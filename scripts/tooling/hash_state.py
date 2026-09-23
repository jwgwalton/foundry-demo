from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest import ToolingManifest


STATE_DIR = Path(".tooling-state")
STATE_FILE = STATE_DIR / "toolbox-fingerprint.json"


@dataclass(frozen=True)
class FingerprintState:
    fingerprint: str
    toolbox_name: str | None = None
    toolbox_version: str | None = None


def _hash_file(hasher: "hashlib._Hash", path: Path, repo_root: Path) -> None:
    relative_path = path.relative_to(repo_root).as_posix()
    hasher.update(f"file:{relative_path}\n".encode("utf-8"))
    hasher.update(path.read_bytes())
    hasher.update(b"\n")


def _hash_directory(hasher: "hashlib._Hash", path: Path, repo_root: Path) -> None:
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        _hash_file(hasher, child, repo_root)


def _hash_optional_path(hasher: "hashlib._Hash", repo_root: Path, value: Any) -> None:
    if not value:
        return

    path = repo_root / str(value)
    if path.is_file():
        _hash_file(hasher, path, repo_root)
    elif path.is_dir():
        _hash_directory(hasher, path, repo_root)


def compute_fingerprint(
    manifest: ToolingManifest,
    repo_root: Path,
    tooling_root: Path,
) -> str:
    hasher = hashlib.sha256()

    for manifest_file in ("connections.yaml", "knowledge-sources.yaml", "toolbox.yaml"):
        _hash_file(hasher, tooling_root / manifest_file, repo_root)

    for tool in manifest.toolbox.get("tools", []):
        _hash_optional_path(hasher, repo_root, tool.get("spec"))

    for source in manifest.knowledge_sources:
        _hash_optional_path(hasher, repo_root, source.get("sourcePath"))

    return hasher.hexdigest()


def load_state(state_file: Path = STATE_FILE) -> FingerprintState | None:
    if not state_file.is_file():
        return None

    data = json.loads(state_file.read_text(encoding="utf-8"))
    return FingerprintState(
        fingerprint=data["fingerprint"],
        toolbox_name=data.get("toolboxName"),
        toolbox_version=data.get("toolboxVersion"),
    )


def save_state(
    fingerprint: str,
    toolbox_name: str,
    toolbox_version: str,
    state_file: Path = STATE_FILE,
) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "toolboxName": toolbox_name,
                "toolboxVersion": toolbox_version,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )