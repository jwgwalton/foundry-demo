from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .azd_cli import (
    add_toolbox_connections_from_file,
    create_toolbox_from_file,
    publish_toolbox_version,
    toolbox_exists,
)
from .manifest import ToolingManifest


@dataclass(frozen=True)
class CreatedToolboxVersion:
    name: str
    version: str



def _toolbox_payload(manifest: ToolingManifest) -> dict:
    knowledge_sources = {source["name"]: source for source in manifest.knowledge_sources}
    tools = []
    for tool in manifest.toolbox.get("tools", []):
        tool_payload = dict(tool)
        knowledge_source_name = tool_payload.pop("knowledgeSource", None)
        if knowledge_source_name:
            source = knowledge_sources[knowledge_source_name]
            if tool_payload["type"] == "azure_ai_search":
                tool_payload.setdefault("azure_ai_search", {})
                tool_payload["azure_ai_search"].setdefault(
                    "indexes",
                    [
                        {
                            "project_connection_id": tool_payload.pop("connection"),
                            "index_name": source["indexName"],
                        }
                    ],
                )
        tools.append(tool_payload)

    payload: dict = {
        "description": manifest.toolbox.get("description", "Foundry toolbox"),
        "tools": tools,
    }
    connections = [
        {"name": connection["name"]}
        for connection in manifest.connections
        if connection.get("type") != "none"
    ]
    if connections:
        payload["connections"] = connections
    policies = manifest.toolbox.get("policies")
    if policies:
        payload["policies"] = policies
    skills = manifest.toolbox.get("skills")
    if skills:
        payload["skills"] = skills
    return payload


def write_azd_toolbox_file(manifest: ToolingManifest) -> Path:
    state_dir = Path(".tooling-state")
    state_dir.mkdir(parents=True, exist_ok=True)
    toolbox_file = state_dir / "toolbox.azd.yaml"
    toolbox_file.write_text(
        yaml.safe_dump(_toolbox_payload(manifest), sort_keys=False),
        encoding="utf-8",
    )
    return toolbox_file


def _connection_mutation_payload(manifest: ToolingManifest) -> dict:
    knowledge_sources = {source["name"]: source for source in manifest.knowledge_sources}
    connections: list[dict[str, str]] = []
    seen: set[tuple[str, str | None]] = set()
    for tool in manifest.toolbox.get("tools", []):
        connection_name = tool.get("connection")
        if not connection_name or connection_name == "none":
            continue

        connection_payload = {"name": connection_name}
        knowledge_source_name = tool.get("knowledgeSource")
        if tool.get("type") == "azure_ai_search" and knowledge_source_name:
            source = knowledge_sources[knowledge_source_name]
            connection_payload["index"] = source["indexName"]

        key = (connection_payload["name"], connection_payload.get("index"))
        if key not in seen:
            connections.append(connection_payload)
            seen.add(key)

    return {"connections": connections}


def write_azd_toolbox_connections_file(manifest: ToolingManifest) -> Path:
    state_dir = Path(".tooling-state")
    state_dir.mkdir(parents=True, exist_ok=True)
    connections_file = state_dir / "toolbox-connections.azd.yaml"
    connections_file.write_text(
        yaml.safe_dump(_connection_mutation_payload(manifest), sort_keys=False),
        encoding="utf-8",
    )
    return connections_file


def _extract_version(value: dict) -> str:
    candidates = [
        value.get("version"),
        value.get("default_version"),
        value.get("defaultVersion"),
    ]
    nested_version = value.get("version")
    if isinstance(nested_version, dict):
        candidates.insert(0, nested_version.get("version"))
    toolbox = value.get("toolbox")
    if isinstance(toolbox, dict):
        candidates.extend([toolbox.get("default_version"), toolbox.get("defaultVersion")])

    for candidate in candidates:
        if candidate:
            return str(candidate)
    return ""


def create_toolbox_version(manifest: ToolingManifest) -> CreatedToolboxVersion:
    toolbox_name = os.environ.get("TOOLBOX_NAME") or manifest.toolbox["name"]
    toolbox_file = write_azd_toolbox_file(manifest)
    if toolbox_exists(toolbox_name):
        connections = _connection_mutation_payload(manifest)["connections"]
        if not connections:
            raise RuntimeError(
                f"Toolbox {toolbox_name} already exists, and no connection mutation "
                "could be generated from tooling/toolbox.yaml. Toolbox versions are "
                "created by azd mutation commands; do not hand-edit a version number "
                "in code."
            )
        connections_file = write_azd_toolbox_connections_file(manifest)
        toolbox = add_toolbox_connections_from_file(toolbox_name, connections_file)
        version = _extract_version(toolbox)
        if not version:
            raise RuntimeError(f"Could not determine new toolbox version for {toolbox_name}.")
        publish_toolbox_version(toolbox_name, version)
    else:
        toolbox = create_toolbox_from_file(toolbox_name, toolbox_file)
        version = _extract_version(toolbox)
    endpoint = toolbox.get("endpoint") or toolbox.get("mcpEndpoint")

    print(f"Created or updated toolbox {toolbox_name}")
    if version:
        print(f"Toolbox version: {version}")
    if endpoint:
        print(f"Toolbox MCP endpoint: {endpoint}")

    if Path(".env").is_file():
        print(
            "Update TOOLBOX_VERSION in .env if needed, then run "
            "scripts/sync_env_to_azd.py."
        )

    return CreatedToolboxVersion(name=str(toolbox.get("name") or toolbox_name), version=version)