"""
A concrete implementation of toolbox creation 

In a CI/CD pipeline i would have to check the versioning and either only run on change or 
"""
import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPToolboxTool, WebSearchToolboxTool
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
toolbox_name = os.environ["TOOLBOX_NAME"]

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):

    # TODO: Make sure if this reruns it doesn't create a new version unless it's actually changed
    created = project_client.toolboxes.create_version(
        name=toolbox_name,
        description="Toolbox with web search",
        tools=[
            WebSearchToolboxTool(
                name="web_search",
                search_context_size="medium",
            )
        ],
    )
    print(f"Created toolbox version {created.version} for {created.name}")

    mcp_endpoint = (
        f"{endpoint}/toolboxes/{created.name}/versions/"
        f"{created.version}/mcp?api-version=v1"
    )
    print(f"Toolbox version: {created.version}")
    print(f"Toolbox MCP endpoint: {mcp_endpoint}")