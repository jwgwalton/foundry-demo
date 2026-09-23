from __future__ import annotations

import os
from pathlib import Path

from .azd_cli import connection_exists, create_connection, ensure_azd_available
from .knowledge_sources import sync_azure_ai_search_file_source
from .manifest import ToolingManifest


def _required_env_names(manifest: ToolingManifest) -> list[str]:
    names = {"FOUNDRY_PROJECT_ENDPOINT"}
    for connection in manifest.connections:
        target_env = connection.get("targetEnv")
        if target_env:
            names.add(target_env)
        secret_env = connection.get("secretEnv")
        if secret_env:
            names.add(secret_env)
        for item in connection.get("customKeys", []):
            item_secret_env = item.get("secretEnv")
            if item_secret_env:
                names.add(item_secret_env)

    for source in manifest.knowledge_sources:
        search_endpoint_env = source.get("searchEndpointEnv")
        if search_endpoint_env:
            names.add(search_endpoint_env)
        embedding = source.get("embeddingModel", {})
        for field in ("resourceUriEnv", "deploymentIdEnv", "modelNameEnv"):
            env_name = embedding.get(field)
            if env_name:
                names.add(env_name)
    return sorted(names)


def preflight_deployment_context(manifest: ToolingManifest) -> None:
    ensure_azd_available()
    missing = [name for name in _required_env_names(manifest) if not os.environ.get(name)]
    if missing:
        raise ValueError(
            "Missing required environment variable(s): " + ", ".join(missing) + "."
        )

    print("Deployment context:")
    print(f"  Foundry project endpoint: {os.environ['FOUNDRY_PROJECT_ENDPOINT'].rstrip('/')}")
    for source in manifest.knowledge_sources:
        if source.get("type") != "azure_ai_search_file":
            continue
        search_endpoint_env = source["searchEndpointEnv"]
        embedding = source["embeddingModel"]
        print(f"  Search endpoint ({search_endpoint_env}): {os.environ[search_endpoint_env]}")
        print(
            f"  Embedding endpoint ({embedding['resourceUriEnv']}): "
            f"{os.environ[embedding['resourceUriEnv']]}"
        )
        print(
            f"  Embedding deployment ({embedding['deploymentIdEnv']}): "
            f"{os.environ[embedding['deploymentIdEnv']]}"
        )
        print(
            f"  Embedding model ({embedding['modelNameEnv']}): "
            f"{os.environ[embedding['modelNameEnv']]}"
        )


def _named(items: list[dict], kind: str) -> dict[str, dict]:
    named_items: dict[str, dict] = {}
    for item in items:
        name = item.get("name")
        if not name:
            raise ValueError(f"Every {kind} entry must define a name.")
        if name in named_items:
            raise ValueError(f"Duplicate {kind} name: {name}")
        named_items[name] = item
    return named_items


def validate_manifest(manifest: ToolingManifest, repo_root: Path) -> None:
    toolbox_name = manifest.toolbox.get("name")
    if not toolbox_name:
        raise ValueError("toolbox.yaml must define a toolbox name.")

    tools = manifest.toolbox.get("tools", [])
    if not tools:
        raise ValueError("toolbox.yaml must define at least one tool.")

    connections = _named(manifest.connections, "connection")
    knowledge_sources = _named(manifest.knowledge_sources, "knowledge source")

    for source in manifest.knowledge_sources:
        source_type = source.get("type")
        source_name = source.get("name")
        source_path = source.get("sourcePath")
        if not source_type or not source_name:
            raise ValueError("Every knowledge source must define name and type.")
        if source_type == "azure_ai_search_file":
            required = ["searchEndpointEnv", "sourcePath", "indexName", "embeddingModel"]
            missing = [field for field in required if field not in source]
            if missing:
                raise ValueError(
                    f"Knowledge source {source_name} is missing required fields: "
                    f"{', '.join(missing)}."
                )
            embedding = source["embeddingModel"]
            for field in ("resourceUriEnv", "deploymentIdEnv", "modelNameEnv"):
                if field not in embedding:
                    raise ValueError(
                        f"Knowledge source {source_name} embeddingModel is missing {field}."
                    )
        if source_path and not (repo_root / source_path).exists():
            raise ValueError(
                f"Knowledge source {source_name} references missing sourcePath {source_path}."
            )

    for tool in tools:
        tool_name = tool.get("name")
        tool_type = tool.get("type")
        if not tool_name or not tool_type:
            raise ValueError("Every toolbox tool must define name and type.")

        connection_name = tool.get("connection")
        if connection_name and connection_name != "none" and connection_name not in connections:
            raise ValueError(
                f"Tool {tool_name} references missing connection {connection_name}."
            )

        knowledge_source_name = tool.get("knowledgeSource")
        if knowledge_source_name and knowledge_source_name not in knowledge_sources:
            raise ValueError(
                f"Tool {tool_name} references missing knowledge source "
                f"{knowledge_source_name}."
            )

        spec = tool.get("spec")
        if spec and not (repo_root / spec).is_file():
            raise ValueError(f"Tool {tool_name} references missing OpenAPI spec {spec}.")

    print(f"Validated toolbox manifest for {toolbox_name} with {len(tools)} tool(s).")


def ensure_connections(manifest: ToolingManifest) -> None:
    for connection in manifest.connections:
        name = connection["name"]
        create = connection.get("create", "manual")
        if connection.get("type") == "none" or create == "not_required":
            print(f"Connection {name}: not required")
        elif connection_exists(name):
            print(f"Connection {name}: exists")
        elif create == "azd":
            create_connection(connection)
            if not connection_exists(name):
                raise ValueError(
                    f"Connection {name} was created but could not be verified with "
                    "azd ai connection show."
                )
            print(f"Connection {name}: created and verified")
        else:
            raise ValueError(
                f"Connection {name} is required but was not found. Create it "
                "before toolbox deployment, or set create: azd with the required "
                "CLI metadata."
            )


def sync_knowledge_sources(manifest: ToolingManifest, repo_root: Path) -> None:
    if not manifest.knowledge_sources:
        print("No knowledge sources declared.")
        return

    for source in manifest.knowledge_sources:
        source_type = source.get("type")
        if source_type == "azure_ai_search_file":
            sync_azure_ai_search_file_source(source, repo_root)
        else:
            print(
                f"Knowledge source {source['name']}: sync is not implemented yet "
                f"for type {source.get('type', '<missing>')}."
            )