# Repository Architecture

## Purpose

This repository contains all Microsoft Foundry agent application code in one
place while keeping each agent independently buildable and deployable. It also
owns the desired definitions and deployment code for Foundry toolboxes.

The repository does not own the Azure environments in which these components
run. Foundry projects, Azure Container Registry (ACR), networking, monitoring,
RBAC, and other foundational resources are provisioned elsewhere and supplied
to pipelines as environment-specific configuration.

## Design Goals

- Keep all agent-related source visible in one repository.
- Build, test, version, and deploy each agent independently.
- Build a separate container image for each hosted agent.
- Define and reconcile Foundry toolboxes programmatically.
- Reuse Azure DevOps pipeline behavior without coupling agent releases.
- Consume existing environments without duplicating their infrastructure code.
- Promote immutable image and toolbox versions between environments.

## Proposed Structure

```text
foundry-agents/
|-- agents/
|   |-- weather-agent/
|   |   |-- src/
|   |   |-- tests/
|   |   |-- evals/
|   |   |-- .foundry/
|   |   |   `-- agent-metadata.yaml
|   |   |-- azure.yaml
|   |   |-- Dockerfile
|   |   |-- pyproject.toml
|   |   `-- uv.lock
|   `-- support-agent/
|       `-- ...
|-- toolboxes/
|   |-- definitions/
|   |   |-- web-search.yaml
|   |   `-- enterprise-search.yaml
|   |-- src/toolbox_deployer/
|   |   |-- cli.py
|   |   |-- models.py
|   |   `-- reconcile.py
|   |-- tests/
|   |-- pyproject.toml
|   `-- uv.lock
|-- pipelines/
|   |-- agents/
|   |   |-- weather-agent.yml
|   |   `-- support-agent.yml
|   |-- templates/
|   |   |-- build-agent.yml
|   |   |-- test-agent.yml
|   |   |-- deploy-agent.yml
|   |   `-- deploy-toolbox.yml
|   `-- toolboxes.yml
|-- docs/
`-- README.md
```

The names are illustrative. Agent directories should use stable names that
also work as ACR repository and Foundry agent names.

## Agent Boundary

Each directory under `agents/` is an independently deployable hosted agent. It
owns:

- application source and prompts;
- agent-specific local tools;
- unit, integration, and evaluation tests;
- its Python dependency manifest and lock file;
- its Dockerfile and container startup command;
- its Foundry deployment declaration in `azure.yaml`; and
- its local Foundry evaluation metadata under `.foundry/`.

Keeping these files together makes the deployable unit obvious. A change to one
agent does not require rebuilding unrelated agents, and different agents can
use different dependencies or runtime settings without conflict.

Foundry and `azd` commands should run with the agent directory as their working
directory. This is important because `azure.yaml`, `.foundry/`, and the source
paths are resolved from that agent root.

## Why There Is No `infra/` Directory

An `infra/` directory would normally contain Bicep or Terraform for resources
such as Foundry accounts and projects, ACR, Key Vault, private networking,
Application Insights, and RBAC assignments.

Those resources are managed outside this repository. Adding their definitions
here would create two owners for the same environment and make application
releases dependent on foundational infrastructure changes. This repository
instead consumes environment outputs through Azure DevOps variables, variable
groups, deployment artifacts, or an approved configuration store.

Typical inputs include:

```text
FOUNDRY_PROJECT_ENDPOINT
AZURE_AI_PROJECT_ID
AZURE_AI_MODEL_DEPLOYMENT_NAME
AZURE_CONTAINER_REGISTRY_NAME
AZURE_SUBSCRIPTION_ID
AZURE_TENANT_ID
```

Authentication should use Azure DevOps workload identity federation and
`DefaultAzureCredential`. Client secrets should not be committed, embedded in
container images, or passed as ordinary environment configuration.

## Why There Is No Shared `packages/` Directory

A shared `packages/` directory is useful when multiple agents need a stable,
versioned implementation of behavior such as telemetry setup, authentication,
domain contracts, or protocol hosting. It is not useful merely because two
agents currently have similar code.

Introducing a shared runtime package too early creates coupling between image
builds and makes dependency ownership less clear. Agents should remain
self-contained until repeated code has a proven shared lifecycle and API. A
shared package can be added later without changing the top-level deployment
model.

## Programmatic Toolbox Management

Toolboxes are managed as desired state. Human-readable definition files state
what each toolbox should contain; a deployment CLI applies those definitions to
the target Foundry project.

For example:

```powershell
uv run python -m toolbox_deployer.cli apply `
    --definition toolboxes/definitions/web-search.yaml
```

The target environment is supplied through pipeline authentication and
environment variables rather than being encoded in the definition.

### Definition Responsibilities

A toolbox definition should contain only portable desired state:

- logical toolbox name;
- description;
- tools and their configuration;
- references to connection names expected in the target project; and
- optional labels used for ownership or deployment policy.

It should not contain subscription IDs, credentials, access tokens, or
environment-specific endpoints.

### Reconciliation Algorithm

The toolbox deployment code should:

1. Parse and schema-validate the requested definition.
2. Resolve the target Foundry project from pipeline configuration.
3. Fetch the latest deployed version of the named toolbox, if one exists.
4. Normalize both definitions by removing server-generated fields and sorting
   order-insensitive collections.
5. Compare a deterministic serialization or hash of the desired and deployed
   definitions.
6. Reuse the current version when they match.
7. Create a new immutable toolbox version when they differ.
8. Emit the toolbox name, version, definition hash, and MCP endpoint as pipeline
   outputs.

This makes repeated pipeline runs idempotent while retaining Foundry's immutable
version history. A new version represents an actual definition change, not just
another pipeline execution.

### Toolbox Output Contract

The toolbox pipeline should publish a machine-readable manifest, for example:

```json
{
  "toolboxes": {
    "web-search": {
      "version": "3",
      "definitionHash": "sha256:...",
      "mcpEndpoint": "https://.../toolboxes/web-search/versions/3/mcp?api-version=v1"
    }
  }
}
```

Agent deployment pipelines consume the exact toolbox version from this
manifest. They should not discover "latest" at runtime because that makes a
deployed agent version non-reproducible.

## Pipeline Responsibilities

### Agent Continuous Integration

An agent CI pipeline should run only when that agent, a pipeline template, or a
relevant repository-wide configuration changes. It should:

1. Install dependencies from the agent's lock file.
2. Run linting, type checks, tests, and evaluations required for that agent.
3. Build using the agent's Dockerfile.
4. Scan the image and generate provenance or an SBOM where required.
5. Push the image to its own ACR repository.
6. Publish the image repository, Git commit, tag, and digest as an artifact.

Use the Git commit as a readable tag, but use the image digest as the immutable
input to deployment.

### Agent Deployment

An agent deployment pipeline should consume an existing image artifact and an
existing toolbox manifest. It should not rebuild either one. It should:

1. Select an approved target environment.
2. Authenticate through workload identity federation.
3. Resolve the external environment configuration.
4. deploy a new immutable Foundry agent version using the image digest and exact
   toolbox versions;
5. run a protocol-level smoke test; and
6. record the deployed agent version and endpoint.

Environment promotion therefore deploys the same image digest and toolbox
definition hash that were validated earlier.

### Toolbox Deployment

The toolbox pipeline should run when toolbox definitions or reconciliation code
changes. It validates all definitions, applies only the selected or changed
definitions, and publishes the output manifest for agent deployments.

## Dependency Direction

The intended dependency flow is:

```text
external environment configuration
              |
              v
toolbox definitions --> toolbox versions
                              |
                              v
agent source --> container image --> Foundry agent version
```

Toolboxes do not depend on agent deployments. Agent builds do not depend on a
live Foundry environment. Only deployment combines an immutable image with
specific toolbox versions and environment configuration.

## Repository Rules

- Do not import source directly from another agent directory.
- Do not place secrets or target-environment identifiers in toolbox definitions.
- Do not use mutable image tags such as `latest` in deployment pipelines.
- Do not resolve the latest toolbox version from agent runtime code.
- Do not rebuild an image during environment promotion.
- Add shared runtime packages only when their ownership and release contract are
  explicit.
- Keep pipeline templates generic; keep agent-specific values in the thin
  per-agent pipeline.

These rules preserve the readability of one repository while maintaining the
release isolation normally provided by separate repositories.