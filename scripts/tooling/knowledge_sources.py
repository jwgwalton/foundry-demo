from __future__ import annotations

import json
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from .hash_state import STATE_DIR


KNOWLEDGE_FILE_STATE = STATE_DIR / "knowledge-source-files.json"
SEARCH_SCOPE = "https://search.azure.com/.default"

# Azure AI Search file knowledge sources are a preview surface. The Learn docs
# show SDK methods such as SearchIndexClient.upload_knowledge_source_file and
# models such as FileKnowledgeSource, but the REST contract is available now:
# https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-file?pivots=rest
# We tried azure-search-documents 11.7.0b1 and 12.0.0; neither exposed those
# file-operation methods or models in this environment. Use the documented
# 2026-08-01-preview REST APIs directly until the Python package exposes the
# preview methods and models.


@dataclass(frozen=True)
class LocalKnowledgeFile:
    path: Path
    relative_name: str
    digest: str


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Environment variable {name} is required.")
    return value


def _source_files(source_path: Path, repo_root: Path) -> list[LocalKnowledgeFile]:
    if not source_path.is_dir():
        raise ValueError(f"Knowledge source path is not a directory: {source_path}")

    files: list[LocalKnowledgeFile] = []
    for path in sorted(item for item in source_path.rglob("*") if item.is_file()):
        relative_name = path.relative_to(source_path).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            LocalKnowledgeFile(
                path=path,
                relative_name=relative_name,
                digest=digest,
            )
        )
    if not files:
        raise ValueError(f"Knowledge source path has no files: {source_path.relative_to(repo_root)}")
    return files


def _load_file_state() -> dict[str, Any]:
    if not KNOWLEDGE_FILE_STATE.is_file():
        return {}
    return json.loads(KNOWLEDGE_FILE_STATE.read_text(encoding="utf-8"))


def _save_file_state(state: dict[str, Any]) -> None:
    KNOWLEDGE_FILE_STATE.parent.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_FILE_STATE.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _search_headers(credential: TokenCredential) -> dict[str, str]:
    token = credential.get_token(SEARCH_SCOPE).token
    return {"Authorization": f"Bearer {token}"}


def _knowledge_source_url(endpoint: str, name: str, api_version: str) -> str:
    return f"{endpoint.rstrip('/')}/knowledgesources/{quote(name)}?api-version={api_version}"


def _knowledge_source_files_url(endpoint: str, name: str) -> str:
    return f"{endpoint.rstrip('/')}/knowledgesources/{quote(name)}/files"


def _knowledge_source_file_url(endpoint: str, name: str, file_id: str, api_version: str) -> str:
    return (
        f"{endpoint.rstrip('/')}/knowledgesources/{quote(name)}/files/"
        f"{quote(file_id)}?api-version={api_version}"
    )


def _raise_for_status_with_body(response: httpx.Response) -> None:
    if response.is_success:
        return

    safe_request_headers = {
        key: ("<redacted>" if key.lower() == "authorization" else value)
        for key, value in response.request.headers.items()
    }
    safe_response_headers = {
        key: ("<redacted>" if key.lower() == "authorization" else value)
        for key, value in response.headers.items()
    }
    print("Azure AI Search REST request failed")
    print(f"Request: {response.request.method} {response.request.url}")
    print(f"Request headers: {json.dumps(safe_request_headers, indent=2)}")
    print(f"Status: {response.status_code} {response.reason_phrase}")
    print(f"Response headers: {json.dumps(safe_response_headers, indent=2)}")
    print("Response body:")
    print(response.text)
    response.raise_for_status()


def _create_or_update_file_knowledge_source(
    source: dict[str, Any],
    credential: TokenCredential,
) -> None:
    embedding = source["embeddingModel"]
    payload = {
        "name": source["name"],
        "kind": "file",
        "description": source.get("description", "File knowledge source"),
        "fileParameters": {
            "ingestionParameters": {
                "contentExtractionMode": source.get("contentExtractionMode", "minimal"),
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": _env(embedding["resourceUriEnv"]),
                        "deploymentId": _env(embedding["deploymentIdEnv"]),
                        "modelName": embedding["modelName"],
                    },
                },
            }
        },
    }
    endpoint = _env(source["searchEndpointEnv"])
    api_version = source.get("apiVersion", "2026-08-01-preview")
    response = httpx.put(
        _knowledge_source_url(endpoint, source["name"], api_version),
        headers={**_search_headers(credential), "Prefer": "return=representation"},
        json=payload,
        timeout=240,
    )
    _raise_for_status_with_body(response)
    print(f"Knowledge source {source['name']}: created or updated")


def _list_remote_files(
    source: dict[str, Any],
    credential: TokenCredential,
) -> dict[str, str]:
    endpoint = _env(source["searchEndpointEnv"])
    api_version = source.get("apiVersion", "2026-08-01-preview")
    response = httpx.get(
        _knowledge_source_files_url(endpoint, source["name"]),
        headers=_search_headers(credential),
        params={"api-version": api_version, "pageSize": "200"},
        timeout=240,
    )
    if response.status_code == 404:
        return {}
    _raise_for_status_with_body(response)
    return {
        item.get("fileName") or item.get("file_name"): item.get("fileId") or item.get("file_id")
        for item in response.json().get("value", [])
        if item.get("fileName") or item.get("file_name")
    }


def _delete_remote_file(
    source: dict[str, Any],
    credential: TokenCredential,
    file_id: str,
) -> None:
    endpoint = _env(source["searchEndpointEnv"])
    api_version = source.get("apiVersion", "2026-08-01-preview")
    response = httpx.delete(
        _knowledge_source_file_url(endpoint, source["name"], file_id, api_version),
        headers=_search_headers(credential),
        timeout=240,
    )
    if response.status_code != 404:
        _raise_for_status_with_body(response)


def _upload_file(
    source: dict[str, Any],
    credential: TokenCredential,
    file: LocalKnowledgeFile,
) -> str:
    file_path = file.path
    endpoint = _env(source["searchEndpointEnv"])
    api_version = source.get("apiVersion", "2026-08-01-preview")
    print(f"Knowledge source {source['name']}: uploading {file.relative_name}")
    response = httpx.post(
        _knowledge_source_files_url(endpoint, source["name"]),
        params={"api-version": api_version},
        headers={
            **_search_headers(credential),
            # Upload gotchas: the 2026-08-01-preview endpoint accepts raw
            # application/octet-stream or multipart/form-data. For this demo we
            # use raw upload with JSON files because markdown/plain-text content
            # returned server-side processing failures in this preview endpoint.
            # Search detects file type from bytes and filename, so keep useful
            # extensions in Content-Disposition.
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{file.relative_name}"',
        },
        content=file_path.read_bytes(),
        timeout=240,
    )
    _raise_for_status_with_body(response)
    uploaded_file = response.json()
    return str(uploaded_file.get("fileId") or uploaded_file.get("file_id") or "")


def sync_azure_ai_search_file_source(source: dict[str, Any], repo_root: Path) -> None:
    source_path = repo_root / source["sourcePath"]
    local_files = _source_files(source_path, repo_root)
    state = _load_file_state()
    source_state = state.setdefault(source["name"], {})

    with DefaultAzureCredential() as credential:
        _create_or_update_file_knowledge_source(source, credential)
        remote_files = _list_remote_files(source, credential)

        for file in local_files:
            previous = source_state.get(file.relative_name, {})
            if previous.get("sha256") == file.digest and previous.get("fileId"):
                print(f"Knowledge source {source['name']}: unchanged {file.relative_name}")
                continue

            previous_file_id = previous.get("fileId") or remote_files.get(file.relative_name)
            if previous_file_id:
                _delete_remote_file(source, credential, previous_file_id)

            file_id = _upload_file(source, credential, file)
            source_state[file.relative_name] = {
                "fileId": file_id,
                "sha256": file.digest,
            }
            print(f"Knowledge source {source['name']}: uploaded {file.relative_name}")

    _save_file_state(state)