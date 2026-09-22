# Local Development Reference

## Purpose

This reference captures manual ways to run and debug the travel agent outside
the primary Azure Developer CLI hosted-agent workflow in [RUNBOOK.md](RUNBOOK.md).

Use this file when you need to debug the local Responses host, inspect
`DefaultAzureCredential` behaviour, test toolbox loading directly, or run the
agent in Docker. For normal hosted-agent development, prefer the `azd` workflow
in the runbook.

## When To Use This Reference

Use these steps for:

-   debugging `main.py` directly
-   testing the local Responses endpoint on port `8088`
-   reproducing Docker startup issues
-   checking toolbox name/version environment variables
-   testing non-interactive service principal credentials

Do not use this as the main hosted-agent workflow. The `azure.yaml` project is
set up for Azure Developer CLI and Foundry-hosted agent commands.

## Required Environment Variables

The local agent process expects:

```text
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
TOOLBOX_NAME="agent-tools"
TOOLBOX_VERSION="1"
```

When using service principal credentials, also set:

```text
AZURE_CLIENT_ID="<appId>"
AZURE_TENANT_ID="<tenant>"
AZURE_CLIENT_SECRET="<password>"
```

Keep `.env` local. Do not commit service principal secrets, tenant-specific
secrets or copied command output containing passwords.

## Credential Option A: Local Developer Login

Use this when running the agent directly from your development machine.

```powershell
az login --tenant "<tenant-id>"
az account set --subscription "<subscription-id>"
```

This works when your signed-in user already has the required Foundry permissions.
It is the simplest path for direct local development, but it does not help a
Docker container unless the container also receives usable credentials.

## Credential Option B: Service Principal For Local Containers

Use this when running the agent in Docker with `--env-file .env`, or when you
want repeatable non-interactive credentials for local testing.

Create a service principal:

```powershell
az login --tenant "<tenant-id>"
az account set --subscription "<subscription-id>"

az ad sp create-for-rbac --name "foundry-local-dev"
```

The command returns values similar to:

```json
{
  "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "displayName": "foundry-local-dev",
  "password": "xxxxxxxxxxxxxxxx",
  "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

Assign the service principal access to the Foundry resource:

```powershell
$SP_APP_ID = "<appId-from-create-for-rbac>"
$RESOURCE_GROUP = "<resource-group-name>"
$FOUNDRY_RESOURCE = "<foundry-resource-name>"

$FOUNDRY_RESOURCE_ID = az cognitiveservices account show `
    --name $FOUNDRY_RESOURCE `
    --resource-group $RESOURCE_GROUP `
    --query id `
    --output tsv

az role assignment create `
    --assignee $SP_APP_ID `
    --role "Foundry User" `
    --scope $FOUNDRY_RESOURCE_ID
```

Map the service principal output into `.env`:

```text
AZURE_CLIENT_ID="<appId>"
AZURE_TENANT_ID="<tenant>"
AZURE_CLIENT_SECRET="<password>"
```

## Create Or Update The Toolbox Manually

Create the Foundry toolbox after changing the toolbox definition. The current
first iteration creates a web-search toolbox.

```powershell
uv run python scripts/create_toolboxes.py
```

Record the printed toolbox version and MCP endpoint. Update `.env` with the
toolbox version if a new version is created.

## Run The Agent Directly

Run the agent directly from the repository root:

```powershell
uv run python main.py
```

The service listens on port `8088` unless `PORT` is set.

## Dump Local Traces To A File

For local-only trace debugging, set `OTEL_TRACES_FILE` before starting the
agent:

```text
OTEL_TRACES_FILE=".traces/local-traces.jsonl"
```

Then run the agent directly:

```powershell
uv run python main.py
```

When `OTEL_TRACES_FILE` is set, OpenTelemetry spans are appended to that file
using the local console exporter. The `.traces/` directory is ignored by Git.
Leave `OTEL_TRACES_FILE` empty to use the normal OTLP or Azure Monitor tracing
paths instead.

## Run The Agent In Docker

Build the container:

```powershell
docker build . -t foundry-agent
```

Run the container with local environment variables:

```powershell
docker run --env-file .env -p 8088:8088 foundry-agent
```

For Docker runs, prefer service principal credentials in `.env` because an
interactive `az login` from the host is not automatically available inside the
container.

## Invoke The Local Responses Endpoint

Use the Responses endpoint for a smoke test:

```powershell
Invoke-RestMethod `
    -Uri "http://localhost:8088/responses" `
    -Method Post `
    -ContentType "application/json" `
    -Body (@{
        input = "Use recent web results to tell me whether Lisbon is a good destination in mid-October."
    } | ConvertTo-Json)
```

## Troubleshooting Manual Runs

-   `DefaultAzureCredential` failures usually mean the runtime has neither a
    valid Azure CLI login nor valid `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and
    `AZURE_CLIENT_SECRET` values.
-   Permission failures usually mean the identity does not have `Foundry User` on
    the Foundry resource scope.
-   Toolbox loading failures usually mean `TOOLBOX_NAME` or `TOOLBOX_VERSION` is
    wrong, or the toolbox version was not created in the selected project.
-   Model failures usually mean `AZURE_AI_MODEL_DEPLOYMENT_NAME` does not match a
    deployed model in the Foundry project.