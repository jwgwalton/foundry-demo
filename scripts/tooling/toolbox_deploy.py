from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .azd_cli import create_toolbox_from_file
from .manifest import ToolingManifest


@dataclass(frozen=True)
class CreatedToolboxVersion:
    name: str
    version: str



def _toolbox_payload(manifest: ToolingManifest) -> dict:
    payload: dict = {
        "description": manifest.toolbox.get("description", "Foundry toolbox"),
        "tools": manifest.toolbox.get("tools", []),
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


def create_toolbox_version(manifest: ToolingManifest) -> CreatedToolboxVersion:
    toolbox_name = os.environ.get("TOOLBOX_NAME") or manifest.toolbox["name"]
    toolbox_file = write_azd_toolbox_file(manifest)
    toolbox = create_toolbox_from_file(toolbox_name, toolbox_file)
    version = str(
        toolbox.get("default_version")
        or toolbox.get("defaultVersion")
        or toolbox.get("version")
        or ""
    )
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