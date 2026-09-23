# Tooling Deployment Flow

## Purpose

The hosted agent should consume an already-prepared, versioned toolbox. Toolbox
dependencies such as Foundry connections, Azure AI Search indexes, Foundry IQ
knowledge sources and OpenAPI specifications must be ready before the agent is
deployed or run.

Before running the full deployment, create the Azure AI Search service described
in [AZURE_AI_SEARCH_PREREQUISITES.md](AZURE_AI_SEARCH_PREREQUISITES.md).

This document describes the deployment order and the scaffolded scripts that
will grow as more tools are added.

## Deployment Order

Use this order whenever toolbox tools change:

1.  Sync project values from `.env` into the active azd environment.
2.  Create missing azd-managed Foundry connections and verify all required
  connections exist.
3.  Upload or index knowledge-source data.
4.  Create or update the toolbox. The first deployment uses
  `azd ai toolbox create --from-file`; later deployments create a new immutable
  version with `azd ai toolbox connection add --from-file` and promote it with
  `azd ai toolbox publish`.
5.  Sync the selected `TOOLBOX_NAME` and `TOOLBOX_VERSION` into azd.
6.  Deploy or run the hosted agent.
7.  Smoke-test the agent and inspect traces.

The important invariant is:

> The agent is deployed only after its toolbox version and upstream dependencies
> are ready.

## Repository Layout

Declarative configuration lives under `tooling/`:

```text
tooling/
├── connections.yaml
├── knowledge-sources.yaml
└── toolbox.yaml
```

Deployment code lives under `scripts/`:

```text
scripts/
├── deploy_tooling.py
├── sync_env_to_azd.py
└── tooling/
  ├── azd_cli.py
  ├── hash_state.py
  ├── knowledge_sources.py
    ├── manifest.py
    ├── preflight.py
    └── toolbox_deploy.py
```

Use YAML for desired state and Python for reconciliation:

-   YAML says which connections, knowledge sources and tools should exist.
-   Python validates the desired state, computes fingerprints and orchestrates
  the deployment phases.
-   Azure Developer CLI (`azd`) provisions Foundry project connections and
  toolboxes wherever the CLI supports the operation.

## Why Mix Python And `azd`?

The deployment flow intentionally uses both Python and the Azure Developer CLI.

Use `azd` for resource-facing operations because it is the CI/CD-friendly,
documented deployment surface for Foundry project selection, connection
creation, toolbox creation from YAML, toolbox inspection and version promotion.
Using the CLI keeps deployment logs close to the commands in Microsoft Learn and
avoids hiding provisioning behaviour inside SDK object construction.

Use Python for orchestration because the pipeline needs repo-specific logic that
the CLI does not provide:

-   validate local manifests before cloud calls
-   reject secrets in YAML
-   hash manifests, OpenAPI specs and source data
-   skip unchanged toolbox deployments
-   generate an `azd ai toolbox create --from-file` payload
-   prepare future data-upload and indexing steps
-   provide a single CI/CD entry point

The normal path is therefore: Python decides whether and how to deploy; `azd`
performs Foundry provisioning.

## Manifest Files

### `tooling/connections.yaml`

Declare the Foundry project connections required by toolbox tools. Do not put
secrets in this file.

```yaml
connections:
  - name: web_search
    type: none
    requiredFor:
      - web_search
    create: not_required
```

Future authenticated tools should reference connection names rather than raw
credentials:

```yaml
connections:
  - name: travel-places-api-key
    type: api_key
    kind: remote-tool
    target: https://example.com
    authType: api-key
    secretEnv: PLACES_API_KEY
    requiredFor:
      - places_openapi
    create: azd
```

  The travel review Search connection is created by `azd` with API-key
  authentication. The manifest declares `secretEnv: SEARCH_QUERY_KEY`, so
  `scripts/deploy_tooling.py` exits before creation if that environment variable is
  not populated.

Connection entries with `create: manual` must already exist. Entries with
`create: azd` are created with `azd ai connection create` when missing. Secret
values are read from environment variables such as `PLACES_API_KEY`; they are
never stored in YAML.

### `tooling/knowledge-sources.yaml`

Declare data sources that must be uploaded, indexed or validated before toolbox
creation.

```yaml
knowledgeSources:
  - name: travel-reviews
    type: azure_ai_search_file
    description: Personal travel reviews and preference notes for TravelAgent.
    searchEndpointEnv: AZURE_SEARCH_ENDPOINT
    sourcePath: travel-reviews
    indexName: travel-reviews
    contentExtractionMode: minimal
    apiVersion: 2026-08-01-preview
    embeddingModel:
      resourceUriEnv: AZURE_OPENAI_ENDPOINT
      deploymentIdEnv: AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME
      modelName: text-embedding-3-large
```

The `azure_ai_search_file` type creates or updates an Azure AI Search file
knowledge source using the Azure AI Search `2026-08-01-preview` REST API, then uploads files from
`sourcePath`. This follows the Azure AI Search file knowledge source pattern:
the service processes uploaded files synchronously, extracts text, chunks content
and creates embeddings before upload calls return.

Required environment variables:

```text
AZURE_SEARCH_ENDPOINT="https://<search-service>.search.windows.net"
SEARCH_QUERY_KEY="<search-service-query-key>"
AZURE_OPENAI_ENDPOINT="https://<openai-resource>.openai.azure.com"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME="text-embedding-3-large"
```

The identity running the sync must have permission to create knowledge sources on
Azure AI Search, for example `Search Service Contributor`. The Azure AI Search
service also needs access to the Azure OpenAI embedding deployment, usually via
managed identity and `Cognitive Services User` on the Foundry/OpenAI resource.

Future Foundry IQ-backed review data can be added here:

```yaml
knowledgeSources:
  - name: travel-review-memory
    type: foundry_iq
    sourcePath: travel-reviews
    indexName: travel-reviews
    create: manual
```

### `tooling/toolbox.yaml`

Declare the toolbox and tools. The current first version contains only web
search:

```yaml
name: agent-tools
description: Travel planning toolbox

tools:
  - name: web_search
    type: web_search
    search_context_size: medium
```

Future tools should reference declared connections and knowledge sources:

```yaml
tools:
  - name: travel_reviews
    type: azure_ai_search
    knowledgeSource: travel-review-memory
    connection: travel-review-search
```

## Script Modes

Deploy the tooling stack:

```powershell
uv run python scripts/deploy_tooling.py
```

Deployment mode validates local manifests and computes the tooling fingerprint
before cloud calls. If the fingerprint is unchanged, the script skips cloud
reconciliation and toolbox version creation by default. If the fingerprint has
changed, it checks the deployment context, sets the active Foundry project,
ensures required connections exist, syncs changed knowledge-source data and
creates a toolbox version.

Validate local manifests and fingerprints without cloud calls:

```powershell
uv run python scripts/deploy_tooling.py --validate-only
```

Force toolbox version creation even if the fingerprint is unchanged:

```powershell
uv run python scripts/deploy_tooling.py --force
```

Verify or repair cloud dependencies without forcing a new toolbox version when
the fingerprint is unchanged:

```powershell
uv run python scripts/deploy_tooling.py --reconcile
```

## Current Implementation Status

Implemented now:

-   YAML manifest loading
-   manifest validation
-   local validation-only mode for PR checks
-   `azd ai project set` before provisioning operations
-   connection checks through `azd ai connection show`
-   optional connection creation through `azd ai connection create`
-   post-create validation that each required connection exists
-   Azure AI Search file knowledge source creation/update and file upload for
  `travel-reviews/`
-   initial toolbox creation through `azd ai toolbox create --from-file`
-   subsequent toolbox version creation through `azd ai toolbox connection add
  --from-file` followed by `azd ai toolbox publish`
-   local fingerprinting of manifests, OpenAPI specs and declared source paths
  to skip unchanged cloud reconciliation and toolbox deployments
-   generated `.tooling-state/toolbox.azd.yaml` payload for the CLI
-   local file upload state in `.tooling-state/knowledge-source-files.json` to
  skip unchanged file uploads

Designed extension points:

-   creating or validating Azure AI Search indexes
-   uploading local review files to Foundry IQ or another knowledge source
-   expanding toolbox YAML for OpenAPI, file search and Foundry IQ tools
-   creating file-search tools that reference knowledge sources
-   automatically writing the new `TOOLBOX_VERSION` back to `.env` or another
    deployment-state file
-   SDK or REST fallback for toolbox version operations not supported by the CLI

## Fingerprint State

`deploy_tooling.py` computes a SHA-256 fingerprint from:

-   `tooling/connections.yaml`
-   `tooling/knowledge-sources.yaml`
-   `tooling/toolbox.yaml`
-   any OpenAPI spec files referenced by tools
-   any local source directories referenced by knowledge sources

After a successful toolbox version creation, the fingerprint and created toolbox
version are written to `.tooling-state/toolbox-fingerprint.json`. The
`.tooling-state/` directory is ignored by Git because it is local deployment
state.

The script also writes `.tooling-state/toolbox.azd.yaml`, which is the generated
payload passed to `azd ai toolbox create --from-file`. This keeps
`tooling/toolbox.yaml` reviewable while allowing the script to add or omit
CLI-specific fields as needed.

Toolbox versions are owned by `azd` and Foundry. Do not update a version number
in source code. When the toolbox already exists, the script writes
`.tooling-state/toolbox-connections.azd.yaml`, asks `azd` to create a new version
from that connection mutation, then publishes the returned version.

For Azure AI Search file knowledge sources, the script records uploaded file IDs
and SHA-256 hashes in `.tooling-state/knowledge-source-files.json`. If a local
file is unchanged, embedding generation and document upload are skipped. If a
file changed, the script generates a fresh embedding and uploads the updated
document. If a previously uploaded file is removed locally, the script deletes
the stale remote document.

When the fingerprint is unchanged, cloud reconciliation and toolbox version
creation are skipped by default. Use `--reconcile` to check and repair cloud
dependencies without creating a new toolbox version, or use `--force` to create a
new toolbox version anyway:

```powershell
uv run python scripts/deploy_tooling.py --reconcile
uv run python scripts/deploy_tooling.py --force
```

## Recommended Command Sequence

For pull requests, run validation only:

```powershell
uv run python scripts/deploy_tooling.py --validate-only
```

After editing tool manifests or review data:

```powershell
uv run python scripts/sync_env_to_azd.py
uv run python scripts/deploy_tooling.py
uv run python scripts/sync_env_to_azd.py --name TOOLBOX_NAME --name TOOLBOX_VERSION
```

Then deploy or run the agent:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd deploy foundry-demo
Remove-Item Env:\AZURE_DEV_USER_AGENT
```

For local hosted-agent testing through azd:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd ai agent run --no-client
Remove-Item Env:\AZURE_DEV_USER_AGENT
```

## Rules

-   Do not put raw secrets in YAML manifests.
-   Create authenticated Foundry connections before toolbox version creation.
-   Keep toolbox versions immutable and deploy agents against an explicit version.
-   Keep toolbox/data mutation out of `main.py`; the runtime should only load the
    configured toolbox version.
-   Fail before agent deployment when a required connection, spec or knowledge
    source is missing.
-   Track open Azure AI Search file knowledge-source upload issues in
  [../TODO.md](../TODO.md).