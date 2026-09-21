# Wella Foundry Demo --- Iterative Implementation Plan

## Purpose

Build a synthetic, Wella-relevant Professional Salon Support Agent that
demonstrates Microsoft Foundry integration patterns while remaining
deterministic and testable.

The project should be developed as vertical slices. Every iteration must
leave a working agent, add evaluation coverage, and preserve the ability
to identify failures through traces.

## Target end state

The agent can handle a request such as:

> "Bella Hair Studio is asking about PRODUCT-1042. They want 24 units.
> Check the product, determine whether sufficient UK stock is available,
> find the relevant usage guidance, and create a support case recording
> the enquiry."

The final system combines:

-   LangGraph application orchestration.
-   OpenAPI product and inventory services.
-   Foundry connections and authentication.
-   An MCP salon/customer support service.
-   Product knowledge stored in Blob Storage.
-   Local Blob emulation using Azurite.
-   Read and write tools.
-   Approval boundaries for consequential actions.
-   Trace-based error analysis.
-   A growing evaluation dataset.
-   A local-to-Azure deployment path.

## Development principle

Each increment follows the same loop:

1.  Define one new behaviour.
2.  Add or extend evaluation cases.
3.  Implement the smallest capability that satisfies it.
4.  Run unit and integration tests.
5.  Run agent evaluations.
6.  Inspect traces for failures.
7.  Fix the responsible layer rather than blindly changing the prompt.
8.  Add newly discovered failure modes to the evaluation dataset.
9.  Move to the next capability only when the increment is stable.

Evaluation tells us **that** the application failed. Traces tell us
**where and why** it failed.

## Proposed repository

``` text
wella-foundry-demo/
├── src/
│   ├── agent/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── prompts.py
│   │   └── nodes.py
│   └── tools/
├── services/
│   ├── product_api/
│   ├── inventory_api/
│   └── salon_mcp/
├── storage/
│   ├── seed/
│   └── seed_azurite.py
├── evaluations/
│   ├── datasets/
│   ├── evaluators/
│   └── results/
├── tests/
├── infra/
│   ├── docker-compose.yml
│   └── azure/
├── pyproject.toml
└── README.md
```

## Iteration 0 --- Evaluation and tracing foundation

Create the repository, minimal LangGraph application, tracing
configuration, test structure, and evaluation runner.

Initially the agent may use an in-process fake `get_product` function.

Start with approximately five evaluation cases covering product lookup,
unknown products, malformed identifiers, and requests that should not
require tools.

Example:

``` json
{
  "input": "Tell me about PRODUCT-1042",
  "expected_product": "PRODUCT-1042",
  "expected_tools": ["get_product"]
}
```

Capture enough trace information to classify failures into:

-   tool selection
-   argument generation
-   authentication
-   tool execution
-   retrieval
-   reasoning
-   grounding
-   action execution
-   final response

**Exit criterion:** evaluations can be run repeatedly and a failed case
can be traced to individual application/tool steps.

## Iteration 1 --- Anonymous Product OpenAPI

Create a FastAPI Product API with a valid OpenAPI document and explicit,
descriptive `operationId` values.

Initial capability:

``` http
GET /products/{sku}
```

Seed only a few deterministic synthetic products.

Replace the in-process product function with the OpenAPI integration.

Test at three levels:

-   Unit: API behaviour and schemas.
-   Integration: agent/tool client to Product API.
-   Evaluation: natural-language request selects the correct product
    operation and returns grounded data.

Add negative cases including unknown SKU, invalid input, and malformed
upstream response.

**Exit criterion:** the agent reliably answers product questions using
the external OpenAPI service.

## Iteration 2 --- API-key authentication and Foundry connection

Keep business behaviour unchanged but require an API key:

``` http
X-API-Key: <secret>
```

Represent the credential through the appropriate Foundry connection when
running against Foundry.

Test valid, absent and invalid credentials. Ensure secrets are never
included in model context, application output, or traces.

**Exit criterion:** authentication has changed without changing the
agent's business behaviour.

## Iteration 3 --- Inventory and multi-tool composition

Add an Inventory API:

``` http
GET /inventory/{sku}?market=GB
```

Example evaluation:

> "We need 24 units of PRODUCT-1042. Is it an active product and do we
> have enough UK stock?"

The expected behaviour requires product and inventory information.

Add evaluations for:

-   correct tool combination
-   correct market code
-   sufficient/insufficient stock
-   inactive product
-   unknown SKU
-   upstream failures
-   no inference of stock when the inventory service fails

**Exit criterion:** the agent reliably composes multiple structured
tools.

## Iteration 4 --- Salon CRM via MCP

Create a local MCP server representing a fictional professional
salon/customer system.

Initially expose:

``` text
search_salons
get_salon
```

Include intentionally ambiguous fixtures, such as similarly named salons
in different locations.

Example:

> "Bella Hair Studio in Brighton wants 24 units of PRODUCT-1042. Do we
> have enough?"

The agent must resolve the salon and combine MCP with OpenAPI tools.

**Exit criterion:** one LangGraph application successfully composes
OpenAPI and MCP capabilities.

## Iteration 5 --- Product knowledge and Azurite

Run Azurite locally and seed synthetic product and technical guidance.

Example structure:

``` text
product-guidance/
├── PRODUCT-1042-technical-guide.md
├── PRODUCT-1042-safety-guide.md
├── PRODUCT-2091-technical-guide.md
├── colour-consultation-guide.md
└── colour-correction-guide.md
```

Introduce questions requiring both operational data and knowledge
retrieval.

Example:

> "Bella Hair Studio wants 24 PRODUCT-1042s. Do we have sufficient UK
> stock and what mixing ratio is specified in the technical guidance?"

Evaluate:

-   correct document retrieval
-   correct section/evidence
-   grounded answer
-   absence of unsupported technical claims
-   behaviour when no relevant document exists

**Exit criterion:** the agent combines structured operational systems
with unstructured enterprise knowledge.

## Iteration 6 --- Support-case write operation

Extend the MCP service with:

``` text
create_support_case
```

Example:

> "Check whether Bella Hair Studio can order 24 units of PRODUCT-1042,
> find the relevant usage instructions and record their enquiry."

Evaluate whether:

-   exactly one case is created
-   the correct salon ID is used
-   the summary reflects retrieved facts
-   the case is not created if required dependencies fail
-   retries cannot accidentally create duplicate cases

**Exit criterion:** the agent safely performs a low-risk state-changing
action.

## Iteration 7 --- Consequential action and approval

Add a more consequential operation such as:

``` text
reserve_inventory
```

or:

``` text
create_order
```

Separate tools conceptually into:

### Read

-   search salons
-   get salon
-   get product
-   get inventory
-   retrieve guidance

### Low-risk write

-   create support case

### Consequential write

-   reserve inventory
-   create order

The consequential operation must not execute until explicit approval is
present.

Evaluate:

-   no action before approval
-   correct proposed action presented for approval
-   exactly one action after approval
-   stale or changed information is handled appropriately
-   rejection results in no write

**Exit criterion:** the demo illustrates an explicit human-in-the-loop
boundary.

## Iteration 8 --- Migrate infrastructure to Azure

Migrate dependencies independently and rerun the same evaluation suite
after every change.

Suggested sequence:

1.  Deploy Product API.
2.  Deploy Inventory API.
3.  Replace local MCP endpoint with remotely hosted MCP.
4.  Replace Azurite with Azure Blob Storage.
5.  Replace development credentials with production-like
    identity/connection patterns.
6.  Run the LangGraph application as a Foundry hosted agent where
    appropriate.
7.  Package reusable capabilities into Foundry Toolbox where this
    improves reuse/governance.

At intermediate stages, intentionally support hybrid configurations such
as a local agent using Azure APIs while still using local Azurite.

**Exit criterion:** the same application behaviours and evaluations
survive the infrastructure transition.

## Test pyramid

Every capability should be covered at the cheapest useful level.

### Unit tests

Test deterministic business logic, schemas, validation, fixture lookup,
authorization middleware and transformations without invoking an LLM.

### Contract tests

Verify OpenAPI schemas, MCP tool schemas and returned payloads.

### Integration tests

Exercise real local containers and emulators: FastAPI services, MCP and
Azurite.

### Agent evaluations

Test semantic behaviours such as tool choice, argument generation,
grounding and workflow completion.

### Trace/error analysis

For every failed evaluation, determine the failing stage before making a
change.

For example:

``` text
Request: "Does Bella Hair Studio have enough PRODUCT-1042?"

search_salons                         PASS
selected salon SAL-001               PASS
get_product(PRODUCT-1042)            PASS
get_inventory market="UK"            FAIL
expected market="GB"

API response                         400
agent recovery                       FAIL
agent inferred availability          FAIL
final answer                         FAIL
```

The correct fix is then targeted at market-code/tool-contract behaviour
rather than an arbitrary prompt rewrite.

## Evaluation dataset growth

Do not treat the initial evaluation set as fixed.

Every discovered meaningful failure should be considered for inclusion
as a regression case. As functionality expands, evaluation criteria
should expand with it.

The evaluation dataset therefore represents the application's evolving
behavioural contract.

## Recommended milestone sequence

``` text
Evaluation harness
    ↓
Single local function
    ↓
Anonymous OpenAPI
    ↓
Authenticated OpenAPI / Foundry Connection
    ↓
Multiple OpenAPI tools
    ↓
MCP
    ↓
Azurite / knowledge
    ↓
Low-risk writes
    ↓
Approval-controlled actions
    ↓
Azure migration
    ↓
Reusable Foundry Toolbox capabilities
```

The important constraint is that every arrow represents a working,
evaluated application---not an unfinished piece of the final
architecture.
