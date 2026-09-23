from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"


@dataclass(frozen=True)
class AzdResult:
    stdout: str
    stderr: str


def _format_stream(name: str, value: str) -> str:
    content = value.strip()
    if not content:
        return f"{name}: <empty>"
    return f"{name}:\n{content}"


def _azd_env() -> dict[str, str]:
    process_env = os.environ.copy()
    process_env.setdefault("AZURE_DEV_USER_AGENT", AZURE_DEV_USER_AGENT)
    return process_env


def ensure_azd_available() -> None:
    if shutil.which("azd") is None:
        raise RuntimeError("Azure Developer CLI 'azd' was not found on PATH.")


def run_azd(*args: str, sensitive: bool = False) -> AzdResult:
    ensure_azd_available()

    display_args = " ".join(args if not sensitive else (*args[:4], "<redacted>"))
    print(f"Running azd {display_args}")

    completed = subprocess.run(
        ["azd", *args],
        check=False,
        capture_output=True,
        env=_azd_env(),
        text=True,
    )
    if completed.returncode != 0:
        details = [
            f"azd {display_args} failed with exit code {completed.returncode}.",
            f"Working directory: {Path.cwd()}",
            _format_stream("stdout", completed.stdout),
            _format_stream("stderr", completed.stderr),
        ]
        if not completed.stdout.strip() and not completed.stderr.strip():
            details.append("azd produced no output. Rerun the command directly with --debug for CLI diagnostics.")
        raise RuntimeError(
            "\n".join(details)
        )
    return AzdResult(stdout=completed.stdout, stderr=completed.stderr)


def run_azd_json(*args: str) -> dict[str, Any]:
    result = run_azd(*args, "--output", "json")
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        display_args = " ".join(args)
        raise RuntimeError(f"azd {display_args} returned invalid JSON: {exc}") from exc


def set_project(endpoint: str) -> None:
    run_azd("ai", "project", "set", endpoint)


def connection_exists(name: str) -> bool:
    ensure_azd_available()
    completed = subprocess.run(
        ["azd", "ai", "connection", "show", name, "--output", "json"],
        check=False,
        capture_output=True,
        env=_azd_env(),
        text=True,
    )
    return completed.returncode == 0


def toolbox_exists(name: str) -> bool:
    ensure_azd_available()
    completed = subprocess.run(
        ["azd", "ai", "toolbox", "show", name, "--output", "json"],
        check=False,
        capture_output=True,
        env=_azd_env(),
        text=True,
    )
    return completed.returncode == 0


def create_connection(connection: dict[str, Any], replace: bool = False) -> None:
    name = connection["name"]
    kind = connection.get("kind")
    target = connection.get("target")
    target_env = connection.get("targetEnv")
    if not target and target_env:
        target = os.environ.get(target_env)
        if not target:
            raise ValueError(f"Environment variable {target_env} is required for {name}.")
    auth_type = connection.get("authType")
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError(f"Environment variable FOUNDRY_PROJECT_ENDPOINT is required for {name}.")
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
        "--project-endpoint",
        project_endpoint.rstrip("/"),
        "--kind",
        kind,
        "--target",
        target,
        "--auth-type",
        auth_type,
    ]
    if replace:
        args.append("--force")

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


def add_toolbox_connections_from_file(toolbox_name: str, connections_file: Path) -> dict[str, Any]:
    return run_azd_json(
        "ai",
        "toolbox",
        "connection",
        "add",
        toolbox_name,
        "--from-file",
        str(connections_file),
    )


def publish_toolbox_version(toolbox_name: str, version: str) -> dict[str, Any]:
    return run_azd_json("ai", "toolbox", "publish", toolbox_name, version)