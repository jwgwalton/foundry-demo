from __future__ import annotations

import json
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.core.exceptions import HttpResponseError
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchField,
    SearchIndex,
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    VectorSearch,
    VectorSearchProfile,
)
from openai import OpenAI

from .hash_state import STATE_DIR


KNOWLEDGE_FILE_STATE = STATE_DIR / "knowledge-source-files.json"
COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


@dataclass(frozen=True)
class LocalKnowledgeFile:
    relative_name: str
    digest: str
    document: dict[str, Any]


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Environment variable {name} is required.")
    return value


def _source_files(source_path: Path, repo_root: Path) -> list[LocalKnowledgeFile]:
    if not source_path.is_dir():
        raise ValueError(f"Knowledge source path is not a directory: {source_path}")

    files: list[LocalKnowledgeFile] = []
    for path in sorted(source_path.glob("*.json")):
        relative_name = path.relative_to(source_path).as_posix()
        content = path.read_bytes()
        document = json.loads(content)
        if not isinstance(document, dict):
            raise ValueError(f"Knowledge source file must contain a JSON object: {relative_name}")
        document["id"] = hashlib.sha256(relative_name.encode("utf-8")).hexdigest()
        document["sourceFile"] = relative_name
        document["content"] = json.dumps(document, ensure_ascii=False)
        files.append(
            LocalKnowledgeFile(
                relative_name=relative_name,
                digest=hashlib.sha256(content).hexdigest(),
                document=document,
            )
        )
    if not files:
        raise ValueError(
            f"Knowledge source path has no JSON files: {source_path.relative_to(repo_root)}"
        )
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


def _embedding_dimensions(model_name: str) -> int:
    dimensions = {
        "text-embedding-3-large": 3072,
        "text-embedding-3-small": 1536,
        "text-embedding-ada-002": 1536,
    }
    try:
        return dimensions[model_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported embedding model for index dimensions: {model_name}") from exc


def _create_or_update_index(
    source: dict[str, Any],
    index_client: SearchIndexClient,
) -> None:
    embedding = source["embeddingModel"]
    index_name = source["indexName"]
    model_name = _env(embedding["modelNameEnv"])
    vector_profile_name = f"{index_name}-vector-profile"
    vectorizer_name = f"{index_name}-vectorizer"
    semantic_configuration_name = f"{index_name}-semantic-configuration"
    index = SearchIndex(
        name=index_name,
        fields=[
            SearchField(name="id", type="Edm.String", key=True, filterable=True),
            SearchField(
                name="documentType",
                type="Edm.String",
                searchable=True,
                filterable=True,
                facetable=True,
            ),
            SearchField(name="destination", type="Edm.String", searchable=True, filterable=True),
            SearchField(name="visitDate", type="Edm.String", searchable=True, filterable=True),
            SearchField(name="title", type="Edm.String", searchable=True),
            SearchField(name="summary", type="Edm.String", searchable=True),
            SearchField(name="whatWorked", type="Collection(Edm.String)", searchable=True),
            SearchField(name="whatDidNotWork", type="Collection(Edm.String)", searchable=True),
            SearchField(name="weatherNotes", type="Edm.String", searchable=True),
            SearchField(name="futureRecommendation", type="Edm.String", searchable=True),
            SearchField(name="travellerProfile", type="Edm.String", searchable=True),
            SearchField(name="weatherFit", type="Edm.String", searchable=True),
            SearchField(name="tripStyle", type="Edm.String", searchable=True),
            SearchField(name="thingsToAvoid", type="Collection(Edm.String)", searchable=True),
            SearchField(name="scoringGuidance", type="Edm.String", searchable=True),
            SearchField(name="sourceFile", type="Edm.String", filterable=True),
            SearchField(name="content", type="Edm.String", searchable=True),
            SearchField(
                name="contentVector",
                type="Collection(Edm.Single)",
                searchable=True,
                stored=False,
                vector_search_dimensions=_embedding_dimensions(model_name),
                vector_search_profile_name=vector_profile_name,
            ),
        ],
        vector_search=VectorSearch(
            profiles=[
                VectorSearchProfile(
                    name=vector_profile_name,
                    algorithm_configuration_name="hnsw",
                    vectorizer_name=vectorizer_name,
                )
            ],
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name=vectorizer_name,
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=_env(embedding["resourceUriEnv"]),
                        deployment_name=_env(embedding["deploymentIdEnv"]),
                        model_name=model_name,
                    ),
                )
            ],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name=semantic_configuration_name,
            configurations=[
                SemanticConfiguration(
                    name=semantic_configuration_name,
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[
                            SemanticField(field_name="summary")
                        ]
                    )
                )
            ],
        ),
    )
    try:
        index_client.create_or_update_index(index)
    except HttpResponseError as exc:
        raise _search_http_error("create or update Search index", source, exc) from exc
    print(f"Search index {index_name}: created or updated")


def _create_or_update_index_knowledge_source(
    source: dict[str, Any],
    index_client: SearchIndexClient,
) -> None:
    index_name = source["indexName"]
    semantic_configuration_name = f"{index_name}-semantic-configuration"
    knowledge_source = SearchIndexKnowledgeSource(
        name=source["name"],
        description=source.get("description", "Azure AI Search index knowledge source"),
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=index_name,
            semantic_configuration_name=semantic_configuration_name,
        ),
    )
    try:
        index_client.create_or_update_knowledge_source(knowledge_source)
    except HttpResponseError as exc:
        raise _search_http_error("create or update Search knowledge source", source, exc) from exc
    print(f"Knowledge source {source['name']}: references index {index_name}")


def _search_http_error(operation: str, source: dict[str, Any], exc: HttpResponseError) -> RuntimeError:
    status_code = getattr(exc, "status_code", None)
    message = f"Azure AI Search failed to {operation} for {source['name']}: {exc.message}"
    if status_code == 403:
        message += (
            " The deployment identity is authenticated but is not authorized for this "
            "Search operation. For setup, grant the identity Search Index Data Contributor "
            "on the Search service; index or knowledge-source management may also require "
            "Search Service Contributor depending on the operation."
        )
    return RuntimeError(message)


def _changed_files(
    local_files: list[LocalKnowledgeFile],
    previous_source_state: dict[str, Any],
) -> list[LocalKnowledgeFile]:
    changed: list[LocalKnowledgeFile] = []
    for file in local_files:
        previous = previous_source_state.get(file.relative_name, {})
        if previous.get("sha256") != file.digest or previous.get("documentId") != file.document["id"]:
            changed.append(file)
    return changed


def _add_embeddings(
    source: dict[str, Any],
    credential: TokenCredential,
) -> list[LocalKnowledgeFile]:
    source_path = source["_sourcePath"]
    local_files = source["_localFiles"]
    embedding = source["embeddingModel"]
    resource_uri = _env(embedding["resourceUriEnv"])
    deployment_id = _env(embedding["deploymentIdEnv"])
    model_name = _env(embedding["modelNameEnv"])
    token_provider = get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE)
    print(f"  Embedding resource: {resource_uri}")
    print(f"  Embedding deployment: {deployment_id}")
    print(f"  Embedding model: {model_name}")
    with OpenAI(
        base_url=f"{resource_uri.rstrip('/')}/openai/v1/",
        api_key=token_provider,
    ) as openai_client:
        response = openai_client.embeddings.create(
            model=deployment_id,
            input=[file.document["content"] for file in local_files],
            dimensions=_embedding_dimensions(model_name),
        )
    for file, embedding_data in zip(local_files, response.data, strict=True):
        file.document["contentVector"] = embedding_data.embedding
    return local_files


def _ensure_indexing_succeeded(operation: str, results: list[Any]) -> None:
    failures = [result for result in results if not result.succeeded]
    if failures:
        details = "; ".join(
            f"{result.key}: {result.error_message or 'unknown error'}" for result in failures
        )
        raise RuntimeError(f"Azure AI Search {operation} failed: {details}")


def sync_azure_ai_search_file_source(source: dict[str, Any], repo_root: Path) -> None:
    source_path = repo_root / source["sourcePath"]
    local_files = _source_files(source_path, repo_root)
    state = _load_file_state()
    previous_source_state = state.get(source["name"], {})
    endpoint = _env(source["searchEndpointEnv"])
    index_name = source["indexName"]

    with DefaultAzureCredential() as credential:
        with SearchIndexClient(endpoint=endpoint, credential=credential) as index_client:
            _create_or_update_index(source, index_client)

            embedding_source = dict(source)
            embedding_source["_sourcePath"] = source_path
            embedding_source["_localFiles"] = local_files
            files_to_upload = _changed_files(local_files, previous_source_state)
            if files_to_upload:
                embedding_source["_localFiles"] = files_to_upload
                embedded_files = _add_embeddings(embedding_source, credential)
            else:
                embedded_files = []
                print(f"Search index {index_name}: no changed document(s) to upload")

            with SearchClient(
                endpoint=endpoint,
                index_name=index_name,
                credential=credential,
            ) as search_client:
                if embedded_files:
                    try:
                        upload_results = search_client.upload_documents(
                            documents=[file.document for file in embedded_files]
                        )
                    except HttpResponseError as exc:
                        raise _search_http_error("upload documents", source, exc) from exc
                    _ensure_indexing_succeeded("upload", upload_results)
                    print(f"Search index {index_name}: uploaded {len(upload_results)} document(s)")

                current_names = {file.relative_name for file in local_files}
                stale_documents = [
                    {"id": details["documentId"]}
                    for relative_name, details in previous_source_state.items()
                    if relative_name not in current_names and details.get("documentId")
                ]
                if stale_documents:
                    try:
                        delete_results = search_client.delete_documents(documents=stale_documents)
                    except HttpResponseError as exc:
                        raise _search_http_error("delete stale documents", source, exc) from exc
                    _ensure_indexing_succeeded("delete", delete_results)
                    print(
                        f"Search index {index_name}: deleted "
                        f"{len(delete_results)} stale document(s)"
                    )

            _create_or_update_index_knowledge_source(source, index_client)

        state[source["name"]] = {
            file.relative_name: {
                "documentId": file.document["id"],
                "sha256": file.digest,
            }
            for file in local_files
        }

    _save_file_state(state)