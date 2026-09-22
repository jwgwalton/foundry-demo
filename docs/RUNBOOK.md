# Foundry Demo Runbook

## Purpose

This runbook captures the primary Azure Developer CLI workflow for the
Foundry-hosted travel agent demo. The `azure.yaml` file defines the existing
Foundry project, web-search toolbox and hosted Docker agent.

Use this runbook for the normal hosted-agent loop. Manual Python, Docker and
service-principal debugging steps live in
[LOCAL_DEVELOPMENT_REFERENCE.md](LOCAL_DEVELOPMENT_REFERENCE.md).

## Prerequisites

-   Azure CLI authenticated to the tenant that owns the Foundry resource.
-   Azure Developer CLI (`azd`) with the AI plugin available.
-   A Microsoft Foundry project.
-   A deployed model in that Foundry project.
-   Python dependencies installed with `uv` or the project environment.
-   A local `.env` file based on `.env.example`.

## Foundry Project Setup

1.  Create or select a project in Microsoft Foundry.
2.  Deploy a model in the project.
3.  Copy the project endpoint from Foundry.
4.  Set the model deployment name and project endpoint in `.env`:

```text
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
TOOLBOX_NAME="agent-tools"
TOOLBOX_VERSION="1"
```

## Credential Setup For The Agent

For the azd workflow, authenticate the Azure CLI to the tenant and subscription
that own the Foundry project:

```powershell
az login --tenant "<tenant-id>"
az account set --subscription "<subscription-id>"
```

The signed-in identity needs permission to access the Foundry project, toolbox
and hosted agent resources. For direct Python or Docker runs with service
principal credentials, use the local development reference instead.

## Required Project Values

Set these values in `.env` or through your selected azd environment:

```text
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
TOOLBOX_NAME="agent-tools"
TOOLBOX_VERSION="1"
```

Keep `.env` local. Do not commit service principal secrets, tenant-specific
secrets or copied command output containing passwords.

To copy non-secret values from `.env` into the active azd environment, run:

```powershell
uv run python scripts/sync_env_to_azd.py
```

The script skips secret-like values such as `AZURE_CLIENT_SECRET` by default.
It also skips empty values by default. Use `--name` to sync only specific
variables:

```powershell
uv run python scripts/sync_env_to_azd.py `
    --name FOUNDRY_PROJECT_ENDPOINT `
    --name AZURE_AI_MODEL_DEPLOYMENT_NAME `
    --name TOOLBOX_NAME `
    --name TOOLBOX_VERSION
```

## Create Or Update The Toolbox

Create the Foundry toolbox after changing the toolbox definition. The current
first iteration creates a web-search toolbox.

```powershell
uv run python scripts/create_toolboxes.py
```

Record the printed toolbox version and MCP endpoint. Update `.env`, then rerun
the azd env sync script if a new toolbox version is created.

## Run With `azd`

The `azure.yaml` file defines:

-   `ai-project`: existing Foundry project endpoint
-   `agent-tools`: Foundry toolbox service
-   `foundry-demo`: hosted Docker agent using the Responses protocol

Run project-scoped azd commands from the repository root. Set
`AZURE_DEV_USER_AGENT=microsoft_foundry_skill` inline for Foundry azd commands;
do not persist it in `.env`, `azure.yaml` or committed configuration.

Provision or update the project:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd up
Remove-Item Env:\AZURE_DEV_USER_AGENT
```

Run the hosted agent locally through the Azure Developer CLI:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd ai agent run --no-client
Remove-Item Env:\AZURE_DEV_USER_AGENT
```

If a command or flag differs in your installed azd version, check the local help:

```powershell
azd ai agent --help
azd ai agent run --help
```

## Invoke Or Inspect The Agent

Use the agent commands supported by your installed `azd` version to invoke or
inspect the hosted agent. Prefer azd commands for the hosted-agent loop. Use the
manual Responses endpoint smoke test only when debugging the direct local host in
[LOCAL_DEVELOPMENT_REFERENCE.md](LOCAL_DEVELOPMENT_REFERENCE.md).

## Generate A Synthetic Eval Dataset

With the local Responses host running on port 8088, generate and execute 100
balanced travel-planning cases:

```powershell
uv run python scripts/generate_eval_dataset.py
```

The script writes JSONL to `.traces/synthetic-travel-eval.jsonl`. Each row
contains the travel-style, trip-length and continent dimensions, a synthetic
query, execution status, latency and the complete Responses API payload,
including surfaced tool calls and tool outputs.

Generate inputs without calling the agent:

```powershell
uv run python scripts/generate_eval_dataset.py --generate-only
```

After a partial or failed run, preserve completed rows and retry the remaining
case IDs:

```powershell
uv run python scripts/generate_eval_dataset.py --resume
```

Use `--count`, `--seed`, `--endpoint` and `--output` to override the defaults.

## Troubleshooting

-   `azd ai agent run` failures can depend on the installed azd AI plugin
    version. Run `azd ai agent run --help` and follow the local command output.
-   Permission failures usually mean the identity does not have `Foundry User` on
    the Foundry resource scope.
-   Toolbox loading failures usually mean the `agent-tools` toolbox service was
    not provisioned correctly, or the hosted agent was not wired to it through
    `azure.yaml`.
-   Model failures usually mean `AZURE_AI_MODEL_DEPLOYMENT_NAME` does not match a
    deployed model in the Foundry project.
-   For direct `python main.py` or Docker failures, use
    [LOCAL_DEVELOPMENT_REFERENCE.md](LOCAL_DEVELOPMENT_REFERENCE.md).
