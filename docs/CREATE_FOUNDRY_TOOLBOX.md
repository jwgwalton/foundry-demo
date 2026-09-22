# Creating a Microsoft Foundry Toolbox

## Recommended Flow

Toolbox deployment is YAML-driven. Define desired connections, knowledge sources
and tools under `tooling/`, then run the deployment script before deploying the
agent.

See [TOOLING_DEPLOYMENT_FLOW.md](TOOLING_DEPLOYMENT_FLOW.md) for the full
process.

## Create Or Update The Toolbox

```powershell
uv run python scripts/deploy_tooling.py --all
```

If the script creates a new toolbox version, update `TOOLBOX_VERSION` in `.env`
and sync it into azd:

```powershell
uv run python scripts/sync_env_to_azd.py --name TOOLBOX_NAME --name TOOLBOX_VERSION
```
