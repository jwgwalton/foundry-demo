"""Sample 02 - Tool call & tool result messages over the Responses API.

Demonstrates that intermediate tool calls and tool results are surfaced
to the client as ``function_call`` / ``function_call_output`` output
items - in both non-streaming JSON responses and SSE streams.

The agent uses a Foundry-deployed Azure OpenAI chat model and one local
tool, ``get_weather``.

Required environment variables (set in `.env` or your shell):

    FOUNDRY_PROJECT_ENDPOINT        e.g. https://<acct>.services.ai.azure.com/api/projects/<proj>
    AZURE_AI_MODEL_DEPLOYMENT_NAME  e.g. gpt-4o   (defaults to "gpt-4o")
    PORT                            optional, defaults to 8088

Run::

    az login
    cp .env.example .env  # then edit the values
    python main.py

Then in another terminal:

    # Non-streaming -- the JSON `output` array contains 3 items:
    #   [0] function_call(get_weather)
    #   [1] function_call_output(<weather string>)
    #   [2] message(<final assistant text>)
    curl -X POST http://127.0.0.1:8088/responses -H 'Content-Type: application/json' -d '{"input":"What is the weather in Seattle?","model":"gpt-4o"}'

    # Streaming -- you should see the events arrive in this order:
    #   response.output_item.added/done   (function_call)
    #   response.output_item.added/done   (function_call_output)
    #   response.output_item.added        (message)
    #   response.output_text.delta * N
    #   response.output_text.done
    #   response.output_item.done         (message)
    #   response.completed
    curl -N -X POST http://127.0.0.1:8088/responses -H 'Content-Type: application/json' -d '{"input":"What is the weather in Tokyo?","model":"gpt-4o","stream":true}'
"""
from __future__ import annotations

import asyncio
import os
from typing import  List

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from langchain_azure_ai.agents.hosting import ResponsesHostServer
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing
from langchain_azure_ai.tools import AzureAIProjectToolbox
from langchain_core.tools import BaseTool


load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

async def _load_toolbox_tools(toolbox_name: str, toolbox_version: str) -> List[BaseTool]:
    """Fetch the LangChain-compatible tool list from the Foundry Toolbox.

    ``project_endpoint`` is resolved from ``FOUNDRY_PROJECT_ENDPOINT``
    automatically. The credential defaults to ``DefaultAzureCredential``
    (so ``az login`` is enough for local dev). Each call opens a fresh
    MCP session against the toolbox and closes it before returning.
    """
    toolbox = AzureAIProjectToolbox(
        toolbox_name=toolbox_name,
        toolbox_version=toolbox_version
    )
    
    tools = await toolbox.get_tools()
    print(f"Loaded {len(tools)} tool(s) from Foundry toolbox '{toolbox_name}':")
    for t in tools:
        print(f"  - {t.name}")
    return tools


def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    openai_client = project.get_openai_client()
    token_provider = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)

    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=token_provider,
    )


def main() -> None:
    if os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    ):
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        enable_auto_tracing()
    else:
        # auto_configure_azure_monitor resolves App Insights from
        # APPLICATION_INSIGHTS_CONNECTION_STRING first, then falls back to
        # FOUNDRY_PROJECT_ENDPOINT (project-managed App Insights).
        enable_auto_tracing(auto_configure_azure_monitor=True)

    toolbox_name = os.environ["TOOLBOX_NAME"]
    toolbox_version = os.environ["TOOLBOX_VERSION"]

    tools = asyncio.run(_load_toolbox_tools(toolbox_name, toolbox_version))
    graph = create_agent(_build_chat_model(), tools=tools)

    port = int(os.environ.get("PORT", "8088"))
    # ResponsesHostServer adapts the compiled LangGraph runnable into a REST endpoint compatible with the OpenAI Responses protocol
    ResponsesHostServer(graph).run(port=port)


if __name__ == "__main__":
    main()
