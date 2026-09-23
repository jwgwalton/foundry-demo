# Azure AI Search Prerequisites

## Purpose

The travel agent uses Azure AI Search as the backing retrieval store for the
`travel-reviews/` knowledge source. Create the Search service in the Azure
portal before running the tooling deployment script.

Portal reference: [Create a search service in the Azure portal](https://learn.microsoft.com/en-us/azure/search/search-create-service-portal).

## What The Tooling Expects

The repo tooling expects an existing Azure AI Search service and these local or
CI environment values:

```text
AZURE_SEARCH_ENDPOINT="https://<search-service>.search.windows.net"
SEARCH_QUERY_KEY="<search-service-query-key>"
AZURE_OPENAI_ENDPOINT="https://<openai-resource>.openai.azure.com"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME="text-embedding-3-large"
```

`scripts/deploy_tooling.py` uses these values to:

1.  create or verify the Foundry project connection named `travel-review-search`
2.  create or update the Azure AI Search file knowledge source named
    `travel-reviews`
3.  upload files from `travel-reviews/`
4.  include the resulting Azure AI Search index in the Foundry toolbox YAML

## Portal Creation Checklist

Before creating the Search service, decide these fixed service properties:

-   **Name**: globally unique under `search.windows.net`; lowercase letters,
    digits and dashes only. This becomes the endpoint host name.
-   **Region**: choose a region that supports the Azure AI Search and agentic
    retrieval features you need. Prefer the same region as the Foundry/OpenAI
    resource to reduce latency and avoid avoidable data movement.
-   **Tier**: Free is useful for short-lived evaluation, but it has limits and
    cannot scale. Basic or Standard is a safer choice once the demo becomes more
    than a quick experiment.
-   **Compute type**: use the default compute type unless you specifically need
    confidential computing.

Create the service in the portal:

1.  Open the Azure portal.
2.  Select **Create a resource**.
3.  Search for **Azure AI Search**.
4.  Select the subscription and resource group used for this demo.
5.  Enter the service name, region, tier and compute type.
6.  Review and create the service.
7.  After deployment, open the service overview and copy the endpoint URL into
    `AZURE_SEARCH_ENDPOINT`.
8.  Open **Settings** > **Keys** and copy a query key into `SEARCH_QUERY_KEY`
    for Foundry project connection creation.
9.  Open **Settings** > **Identity**, turn on the system-assigned managed
    identity and save. Azure AI Search uses this identity when its vectorizer
    calls the Foundry/OpenAI embedding deployment.

## Demo Search Service Command

For this demo, the Azure AI Search service was created with the Azure CLI rather
than the portal:

```powershell
az search service create `
    --name foundry-demo-ai-search `
    --resource-group rg-joe_fls_test-7033 `
    --sku Standard `
    --partition-count 1 `
    --replica-count 1 `
    --location swedencentral
```

This creates a Standard tier Search service with one partition and one replica in
Sweden Central. After creation, set:

```text
AZURE_SEARCH_ENDPOINT="https://foundry-demo-ai-search.search.windows.net"
SEARCH_QUERY_KEY="<query-key-from-the-search-service>"
```

## Authentication And Roles

Prefer role-based access control rather than admin keys.

The current Foundry project connection is created with `azd ai connection create`
using API-key authentication. The deployment tooling reads the key from
`SEARCH_QUERY_KEY` and fails before invoking `azd` if that variable is missing.
Keep this value in `.env`, the local shell environment or a CI secret provider;
do not commit it.

In the Search service portal page:

1.  Open **Settings** > **Keys**.
2.  Use **Both** while assigning roles, then switch to **Role-based access
    control** when keyless access is working.

Required access:

-   **Developer or CI identity** running `scripts/deploy_tooling.py` needs enough
    Azure AI Search permission to create or update indexes, create knowledge
    sources and upload documents. Use `Search Service Contributor` for Search
    service setup and `Search Index Data Contributor` for document upload during
    the setup phase.
-   **Runtime identity** used by the Foundry toolbox connection needs permission
    to query the resulting Search content. Use the least-privileged Search
    data-plane role that supports the selected toolbox/query path.
-   **Azure AI Search service managed identity** needs `Cognitive Services
    OpenAI User` on the Azure OpenAI/Foundry resource that hosts the embedding
    deployment. Without this, vector queries can fail with: `Could not complete
    vectorization action. The service failed to authenticate to the vectorization
    endpoint.`

If you use private networking, also confirm Search can reach the Foundry/OpenAI
resource according to your network rules.

## Grant Search Access To The Embedding Deployment

Integrated vectorization is performed by the Azure AI Search service, not by the
agent host or the local deployment script. When the index vectorizer references a
Foundry/OpenAI embedding deployment, the Search service must authenticate to that
resource with its managed identity.

For this demo, grant `foundry-demo-ai-search` access to the Azure AI resource
`joe-fls-test-7033-resource`:

```powershell
$resourceGroup = "rg-joe_fls_test-7033"
$searchService = "foundry-demo-ai-search"
$aiResource = "joe-fls-test-7033-resource"

az search service update `
    --name $searchService `
    --resource-group $resourceGroup `
    --identity-type SystemAssigned

$searchPrincipalId = az search service show `
    --name $searchService `
    --resource-group $resourceGroup `
    --query "identity.principalId" `
    -o tsv

$aiResourceId = az cognitiveservices account show `
    --name $aiResource `
    --resource-group $resourceGroup `
    --query "id" `
    -o tsv

az role assignment create `
    --assignee-object-id $searchPrincipalId `
    --assignee-principal-type ServicePrincipal `
    --role "Cognitive Services OpenAI User" `
    --scope $aiResourceId
```

After assigning the role, wait a few minutes for RBAC propagation before testing
Search vector queries or agent tool calls again.

Portal equivalent:

1.  Open the Azure AI Search service.
2.  Go to **Settings** > **Identity**.
3.  Turn **System assigned** to **On** and save.
4.  Open the Azure AI/Foundry resource that hosts the embedding deployment.
5.  Go to **Access control (IAM)** > **Add role assignment**.
6.  Select the `Cognitive Services OpenAI User` role.
7.  Assign access to the managed identity for the Azure AI Search service.

## Embedding Deployment

Deploy a text embedding model in Microsoft Foundry before uploading files. For
this demo, the embedding deployment was created through the Microsoft Foundry UI.

Use the Foundry UI to:

1.  Open the Foundry project or resource used by this demo.
2.  Deploy a text embedding model, such as `text-embedding-3-large`.
3.  Copy the Azure OpenAI/Foundry resource endpoint into `AZURE_OPENAI_ENDPOINT`.
4.  Copy the embedding deployment name into
    `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`.

The current manifest expects:

```text
AZURE_OPENAI_ENDPOINT="https://<openai-resource>.openai.azure.com"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME="text-embedding-3-large"
```

If your deployment name differs, update `.env` and sync the value into the
environment used by CI. The `modelName` in `tooling/knowledge-sources.yaml` must
match the embedding model family, while the deployment name must match the model
deployment you created in Foundry.

## Cost And Limits Notes

-   File knowledge sources are preview functionality and are subject to preview
    limitations.
-   Uploading files can incur Azure AI Search, embedding model and processing
    charges.
-   File knowledge sources have file-count, file-size and processing-time limits.
-   Each upload is synchronous: Search processes, chunks, embeds and indexes the
    file before the call returns.
-   Use `minimal` extraction for JSON travel reviews unless you need richer
    processing.

## Validation

After setting the environment values, run a no-cloud manifest check:

```powershell
uv run python scripts/deploy_tooling.py --validate-only
```

When the Search service, roles and embedding deployment are ready, run the full
tooling deployment:

```powershell
uv run python scripts/deploy_tooling.py
```

If deployment fails, check:

-   `AZURE_SEARCH_ENDPOINT` points at the Search service endpoint.
-   the signed-in or CI identity has Search management and data-plane
    permissions. A `Forbidden` error during document upload usually means the
    identity needs `Search Index Data Contributor` on the Search service.
-   the Search service managed identity can access the embedding deployment.
    For vectorization authentication failures, confirm the Search service has a
    system-assigned managed identity and that identity has `Cognitive Services
    OpenAI User` on the Azure AI/Foundry resource.
-   files under `travel-reviews/` are valid JSON files.
-   the target region supports the required Azure AI Search/agentic retrieval
    capabilities.

Open investigation notes are tracked in [../TODO.md](../TODO.md).