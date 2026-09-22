from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from langchain_azure_ai.agents.hosting import ResponsesHostServer
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing
from langchain_azure_ai.tools import AzureAIProjectToolbox
from langchain_core.tools import BaseTool


load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

AGENT_INSTRUCTIONS = """You are TravelAgent, a travel timing and planning assistant.

Your job is to help users decide whether a destination and travel window are a
good fit by combining available tool evidence with clear reasoning. Start with
current travel context from web search when the user asks about whether now, a
season, or a date range is a good time to visit. Use weather tools when forecast
or climate conditions are relevant. Use personal review or preference retrieval
tools when the user asks whether a destination fits their tastes or when prior
travel memory would improve the recommendation.

Ask a concise clarifying question when the destination or travel dates are too
ambiguous to answer well. Do not claim live weather, current events, personal
preferences, bookings, reservations, prices, or availability unless that
information came from tools or from the user.

Keep recommendations practical and grounded. Separate evidence from judgement:
summarize the tool findings first, then explain the trade-offs, then give a
clear go / wait / adjust-dates recommendation. Mention uncertainty and missing
information when it matters.

Do not make bookings, payments, reservations, calendar entries, or persistent
changes unless the user explicitly approves the exact action and content first.
"""


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


def setup_logging() -> None:
    trace_file = os.environ.get("OTEL_TRACES_FILE")
    if trace_file:
        trace_path = Path(trace_file)
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        provider = TracerProvider()
        trace_output = trace_path.open("a", encoding="utf-8")
        provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter(out=trace_output))
        )
        trace.set_tracer_provider(provider)
        enable_auto_tracing()
        return

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


def main() -> None:
    setup_logging()

    toolbox_name = os.environ["TOOLBOX_NAME"]
    toolbox_version = os.environ["TOOLBOX_VERSION"]

    tools = asyncio.run(_load_toolbox_tools(toolbox_name, toolbox_version))
    graph = create_agent(model=_build_chat_model(), system_prompt=AGENT_INSTRUCTIONS, tools=tools)

    port = int(os.environ.get("PORT", "8088"))
    # ResponsesHostServer adapts the compiled LangGraph runnable into a REST endpoint compatible with the OpenAI Responses protocol
    ResponsesHostServer(graph).run(port=port)


if __name__ == "__main__":
    main()
