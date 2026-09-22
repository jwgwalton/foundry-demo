from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values


AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
SECRET_NAMES = {
    "AZURE_CLIENT_SECRET",
    "AZURE_CLIENT_CERTIFICATE_PATH",
    "AZURE_USERNAME",
    "AZURE_PASSWORD",
}
SECRET_NAME_PATTERN = re.compile(
    r"(SECRET|PASSWORD|TOKEN|PRIVATE_KEY|API_KEY)$",
    re.IGNORECASE,
)


def is_secret_name(name: str) -> bool:
    return name in SECRET_NAMES or bool(SECRET_NAME_PATTERN.search(name))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync values from a .env file into the active azd environment."
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the .env file to read. Defaults to .env.",
    )
    parser.add_argument(
        "--name",
        action="append",
        dest="names",
        help=(
            "Environment variable name to sync. May be passed multiple times, "
            "or as comma-separated values. If omitted, all non-secret, non-empty "
            "values are synced."
        ),
    )
    parser.add_argument(
        "--include-secrets",
        action="store_true",
        help="Also sync secret-like values. Off by default.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Also sync empty values. Off by default.",
    )
    return parser.parse_args()


def normalize_names(names: list[str] | None) -> set[str]:
    if not names:
        return set()

    normalized: set[str] = set()
    for item in names:
        normalized.update(name.strip() for name in item.split(",") if name.strip())
    return normalized


def selected_values(
    env_file: Path,
    requested: set[str],
    include_secrets: bool,
    include_empty: bool,
) -> dict[str, str]:
    parsed = dotenv_values(env_file)
    selected: dict[str, str] = {}

    for name, value in parsed.items():
        if value is None:
            continue
        if requested and name not in requested:
            continue
        if value == "" and not include_empty:
            print(f"Skipping empty value {name}. Use --include-empty to opt in.")
            continue
        if not include_secrets and is_secret_name(name):
            print(f"Skipping secret-like value {name}. Use --include-secrets to opt in.")
            continue
        selected[name] = value

    for name in sorted(requested.difference(parsed.keys())):
        print(f"Warning: requested name {name} was not found in {env_file}.", file=sys.stderr)

    return selected


def sync_to_azd(values: dict[str, str]) -> None:
    process_env = os.environ.copy()
    process_env.setdefault("AZURE_DEV_USER_AGENT", AZURE_DEV_USER_AGENT)

    for name, value in values.items():
        print(f"Setting azd env value: {name}")
        subprocess.run(
            ["azd", "env", "set", name, value],
            check=True,
            env=process_env,
        )


def main() -> int:
    args = parse_args()
    env_file = Path(args.env_file)

    if not env_file.is_file():
        print(f"Environment file not found: {env_file}", file=sys.stderr)
        return 1

    if shutil.which("azd") is None:
        print("Azure Developer CLI 'azd' was not found on PATH.", file=sys.stderr)
        return 1

    values = selected_values(
        env_file=env_file,
        requested=normalize_names(args.names),
        include_secrets=args.include_secrets,
        include_empty=args.include_empty,
    )
    if not values:
        print(f"No environment values selected from {env_file}.")
        return 0

    try:
        sync_to_azd(values)
    except subprocess.CalledProcessError as exc:
        print(f"azd env set failed with exit code {exc.returncode}.", file=sys.stderr)
        return exc.returncode

    print(f"Synced {len(values)} value(s) from {env_file} into the active azd environment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())