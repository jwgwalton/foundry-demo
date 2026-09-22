from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"


@dataclass(frozen=True)
class AzdResult:
    stdout: str
    stderr: str


def run_azd(*args: str, sensitive: bool = False) -> AzdResult:
    process_env = os.environ.copy()
    process_env.setdefault("AZURE_DEV_USER_AGENT", AZURE_DEV_USER_AGENT)

    display_args = " ".join(args if not sensitive else (*args[:4], "<redacted>"))
    print(f"Running azd {display_args}")

    completed = subprocess.run(
        ["azd", *args],
        check=False,
        capture_output=True,
        env=process_env,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"azd {display_args} failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return AzdResult(stdout=completed.stdout, stderr=completed.stderr)


def run_azd_json(*args: str) -> dict[str, Any]:
    result = run_azd(*args, "--output", "json")
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def set_project(endpoint: str) -> None:
    run_azd("ai", "project", "set", endpoint)


def connection_exists(name: str) -> bool:
    completed = subprocess.run(
        ["azd", "ai", "connection", "show", name, "--output", "json"],
        check=False,
        capture_output=True,
        env={**os.environ, "AZURE_DEV_USER_AGENT": os.environ.get("AZURE_DEV_USER_AGENT", AZURE_DEV_USER_AGENT)},
        text=True,
    )
    return completed.returncode == 0


def create_connection(connection: dict[str, Any]) -> None:
    name = connection["name"]
    kind = connection.get("kind")
    target = connection.get("target")
    auth_type = connection.get("authType")
    if not kind or not target or not auth_type:
        raise ValueError(
            f"Connection {name} cannot be created automatically without kind, "
            "target and authType."
        )

    args = [
        "ai",
        "connection",
        "create",
        name,
        "--kind",
        kind,
        "--target",
        target,
        "--auth-type",
        auth_type,
    ]

    if auth_type == "api-key":
        secret_env = connection.get("secretEnv")
        if not secret_env:
            raise ValueError(f"Connection {name} with api-key auth requires secretEnv.")
        secret_value = os.environ.get(secret_env)
        if not secret_value:
            raise ValueError(f"Environment variable {secret_env} is required for {name}.")
        args.extend(["--key", secret_value])
        run_azd(*args, sensitive=True)
        return

    custom_keys = connection.get("customKeys")
    if auth_type == "custom-keys" and custom_keys:
        for item in custom_keys:
            header = item["header"]
            secret_env = item["secretEnv"]
            secret_value = os.environ.get(secret_env)
            if not secret_value:
                raise ValueError(f"Environment variable {secret_env} is required for {name}.")
            args.extend(["--custom-key", f"{header}={secret_value}"])
        run_azd(*args, sensitive=True)
        return

    run_azd(*args)


def create_toolbox_from_file(toolbox_name: str, toolbox_file: Path) -> dict[str, Any]:
    run_azd(
        "ai",
        "toolbox",
        "create",
        toolbox_name,
        "--from-file",
        str(toolbox_file),
        "--no-prompt",
    )
    return run_azd_json("ai", "toolbox", "show", toolbox_name)