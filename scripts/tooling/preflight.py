from __future__ import annotations

from pathlib import Path

from .azd_cli import connection_exists, create_connection
from .manifest import ToolingManifest


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


def check_connections(manifest: ToolingManifest) -> None:
    for connection in manifest.connections:
        name = connection["name"]
        create = connection.get("create", "manual")
        if connection.get("type") == "none" or create == "not_required":
            print(f"Connection {name}: not required")
        elif connection_exists(name):
            print(f"Connection {name}: exists")
        elif create == "azd":
            create_connection(connection)
        else:
            raise ValueError(
                f"Connection {name} is required but was not found. Create it "
                "before toolbox deployment, or set create: azd with the required "
                "CLI metadata."
            )


def sync_knowledge_sources(manifest: ToolingManifest) -> None:
    if not manifest.knowledge_sources:
        print("No knowledge sources declared.")
        return

    for source in manifest.knowledge_sources:
        print(
            f"Knowledge source {source['name']}: sync is not implemented yet "
            f"for type {source.get('type', '<missing>')}."
        )