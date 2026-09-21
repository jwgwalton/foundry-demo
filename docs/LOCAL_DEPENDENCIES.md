# Local Dummy Dependencies

## Purpose

This document defines how the current demo should implement the synthetic
external systems specified in
[Stub APIs and Tooling Specification](02-stub-apis-and-tools-spec.md).

These systems exist only for local development and automated integration tests.
They are not part of the idealized deployment architecture in
[Repository Architecture](REPOSITORY_ARCHITECTURE.md), are not published to
Azure Container Registry, and are not deployed to shared environments.

## Structure

```text
local/
|-- dependencies/
|   |-- src/dummy_systems/
|   |   |-- business_api/
|   |   |   |-- app.py
|   |   |   |-- products.py
|   |   |   `-- inventory.py
|   |   |-- salon_mcp/
|   |   |   `-- server.py
|   |   `-- knowledge_seed/
|   |       `-- seed.py
|   |-- fixtures/
|   |   |-- products/
|   |   |-- inventory/
|   |   |-- salons/
|   |   `-- product-guidance/
|   |-- tests/
|   |-- Dockerfile
|   |-- pyproject.toml
|   `-- uv.lock
`-- compose.yaml
```

This is one Python project with one dependency lock file and one custom
Dockerfile.

## Runtime Topology

Docker Compose builds the dummy-systems image once and starts it with different
commands:

| Compose service | Implementation | Local port |
| --- | --- | ---: |
| `business-api` | Product Catalogue and Inventory FastAPI routes | `8001` |
| `salon-mcp` | Salon CRM MCP server | `8003` |
| `azurite` | Official Azurite image | `10000` |
| `knowledge-seed` | One-shot Azurite seed command | None |

The Product Catalogue and Inventory APIs share one FastAPI process and one
port. Their routes remain separated by path, such as `/products/...` and
`/inventory/...`, with domain-specific route modules and tests.

The Salon MCP server runs as a second container from the same custom image.
This avoids another Dockerfile while keeping REST and MCP as separate processes
with independent health checks and restart behavior. Running both servers in
one container would require unnecessary process supervision.

Azurite uses its official image. The repository owns only the synthetic
documents, metadata, and seed command. The `knowledge-seed` service waits for
Azurite to become healthy, loads deterministic content, and exits successfully.

## Fixtures

All synthetic data belongs under `local/dependencies/fixtures/`, grouped by
domain. Fixtures must:

- use the stable identifiers from the stub specification;
- remain deterministic across runs;
- include the specified negative and error scenarios;
- contain no real customer or commercially sensitive data; and
- be validated by contract and cross-system integration tests.

The services should read fixtures rather than embedding large datasets in
application modules. State-changing MCP operations may write to an ephemeral
test data directory or in-memory store that is reset when the Compose stack is
recreated.

## Local Workflow

Start the dependencies from the repository root:

```powershell
docker compose -f local/compose.yaml up --build
```

Agent configuration should use Compose service names when the agent also runs
inside Compose and `localhost` ports when the agent runs directly on the host.
These values belong in local environment configuration, not in source code.

CI may start the same Compose stack for integration tests, but it should not
push these images to ACR or publish deployment artifacts for them.

## Toolbox Reachability

Managed Foundry toolboxes cannot call `localhost` on a developer machine.
Therefore:

- local agent tests should connect directly to the local OpenAPI and MCP
  endpoints; and
- tests that invoke a managed Foundry toolbox require an explicitly approved,
  network-reachable test endpoint.

Creating a remote toolbox definition that references a local URL does not make
that URL reachable from Foundry. The programmatic toolbox definitions can still
be tested for schema and reconciliation behavior without invoking their backing
local systems through the managed service.

## Scope Boundary

The local dependency project owns dummy behavior, fixtures, health endpoints,
error simulation, and seed operations. It does not own Azure infrastructure,
Foundry resources, shared environment configuration, or deployment pipelines.