from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ToolingManifest:
    toolbox: dict[str, Any]
    connections: list[dict[str, Any]]
    knowledge_sources: list[dict[str, Any]]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream)
    return loaded or {}


def load_manifest(root: Path) -> ToolingManifest:
    toolbox = _load_yaml(root / "toolbox.yaml")
    connections = _load_yaml(root / "connections.yaml").get("connections", [])
    knowledge_sources = _load_yaml(root / "knowledge-sources.yaml").get(
        "knowledgeSources", []
    )
    return ToolingManifest(
        toolbox=toolbox,
        connections=connections,
        knowledge_sources=knowledge_sources,
    )