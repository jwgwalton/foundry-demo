from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from tooling.azd_cli import set_project
from tooling.hash_state import compute_fingerprint, load_state, save_state
from tooling.manifest import load_manifest
from tooling.preflight import (
    ensure_connections,
    preflight_deployment_context,
    sync_knowledge_sources,
    validate_manifest,
)
from tooling.toolbox_deploy import create_toolbox_version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Foundry toolbox dependencies before deploying the agent."
    )
    parser.add_argument(
        "--tooling-root",
        default="tooling",
        help="Directory containing toolbox, connection and knowledge manifests.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate local manifests and fingerprints without calling azd.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Create a toolbox version even when the local fingerprint is unchanged.",
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help=(
            "Run cloud reconciliation even when the local fingerprint is unchanged. "
            "Does not force toolbox version creation."
        ),
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    repo_root = Path.cwd()
    tooling_root = repo_root / args.tooling_root

    try:
        manifest = load_manifest(tooling_root)
        validate_manifest(manifest, repo_root)
        fingerprint = compute_fingerprint(manifest, repo_root, tooling_root)
        previous_state = load_state()

        if args.validate_only:
            print(f"Tooling fingerprint: {fingerprint}")
            return 0

        preflight_deployment_context(manifest)

        fingerprint_unchanged = (
            previous_state is not None and previous_state.fingerprint == fingerprint
        )
        if fingerprint_unchanged and not args.force and not args.reconcile:
            assert previous_state is not None
            print(
                "Tooling fingerprint unchanged; skipping cloud reconciliation and "
                "toolbox version creation. Use --reconcile to verify cloud state or "
                "--force to create a toolbox version. Current recorded version: "
                f"{previous_state.toolbox_version}."
            )
            return 0

        set_project(os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/"))

        ensure_connections(manifest)
        sync_knowledge_sources(manifest, repo_root)

        if fingerprint_unchanged and not args.force:
            assert previous_state is not None
            print(
                "Tooling fingerprint unchanged; skipping toolbox version "
                f"creation. Current recorded version: {previous_state.toolbox_version}."
            )
        else:
            created = create_toolbox_version(manifest)
            save_state(
                fingerprint=fingerprint,
                toolbox_name=created.name,
                toolbox_version=created.version,
            )
    except Exception as exc:
        print(f"Tooling deployment failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())