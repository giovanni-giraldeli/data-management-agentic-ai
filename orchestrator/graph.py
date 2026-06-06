"""LangGraph orchestration graph.

Architecture
------------
The graph implements a **supervisor pattern**:

  START → planner ──(route)──> data_profile_worker ─┐
                  │           metadata_worker        │
                  │           data_modeling_worker   │──> planner → … → END
                  │           data_quality_worker    │
                  └───────── semantical_worker ──────┘

The Planner is the only node that makes routing decisions.  All workers execute
their tasks and always return to the Planner.  The Planner can call workers in any
order and repeat them if needed; it declares FINISH when the pipeline is complete.

MCP tool scoping
----------------
The DuckDB and dbt MCP servers expose the full set of tools.  Each agent node
is built with only the filtered subset that its permissions allow (thesis §4.4.3).
File-system write tools are further scoped by extension via ``make_write_tool``.

Audit trail
-----------
Every agent invocation passes an ``AuditTrailCallback`` configured with the
agent's identifier.  All events are appended to a single JSON Lines log file.

Routing safeguards
------------------
The graph is compiled with ``recursion_limit=MAX_GRAPH_ITERATIONS`` to prevent
infinite Planner↔worker loops if the LLM fails to converge.  The MCP server
startup is wrapped in ``asyncio.timeout`` with ``MCP_STARTUP_TIMEOUT`` seconds
so a missing venv or bad path fails fast instead of hanging.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Annotated, Any, List, Literal, Optional, get_args

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# Local imports
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import (
    AUDIT_LOG_PATH,
    DBT_PROFILES_DIR,
    DBT_PROJECT_DIR,
    DUCKDB_PATH,
    LLM_MODEL,
    LLM_TEMPERATURE,
    MCP_DBT_SERVER,
    MCP_DUCKDB_SERVER,
    PYTHON_EXECUTABLE,  # used by the DuckDB MCP server launch
)
from audit.callbacks import AuditTrailCallback
from tools.filesystem import list_directory, make_write_tool, read_file

from agents.planner import (
    PLANNER_FS_WRITE_EXTENSIONS,
    PLANNER_MCP_TOOLS,
    PLANNER_SYSTEM_PROMPT,
)
from agents.data_profile_worker import (
    DATA_PROFILE_FS_WRITE_EXTENSIONS,
    DATA_PROFILE_MCP_TOOLS,
    DATA_PROFILE_SYSTEM_PROMPT,
)
from agents.metadata_worker import (
    METADATA_FS_WRITE_EXTENSIONS,
    METADATA_MCP_TOOLS,
    METADATA_SYSTEM_PROMPT,
)
from agents.data_modeling_worker import (
    DATA_MODELING_FS_WRITE_EXTENSIONS,
    DATA_MODELING_MCP_TOOLS,
    DATA_MODELING_SYSTEM_PROMPT,
)
from agents.data_quality_worker import (
    DATA_QUALITY_FS_WRITE_EXTENSIONS,
    DATA_QUALITY_MCP_TOOLS,
    DATA_QUALITY_SYSTEM_PROMPT,
)
from agents.semantical_worker import (
    SEMANTICAL_FS_WRITE_EXTENSIONS,
    SEMANTICAL_MCP_TOOLS,
    SEMANTICAL_SYSTEM_PROMPT,
)

# ---------------------------------------------------------------------------
# Safeguard constants
# ---------------------------------------------------------------------------

# Maximum number of graph steps before LangGraph raises GraphRecursionError.
# Each Planner→Worker→Planner round trip costs 2 steps; 100 allows ~50 full
# worker dispatches before the pipeline is forcibly terminated.
MAX_GRAPH_ITERATIONS: int = int(os.getenv("MAX_GRAPH_ITERATIONS", "100"))

# Seconds to wait for both MCP servers to finish starting up.
MCP_STARTUP_TIMEOUT: float = float(os.getenv("MCP_STARTUP_TIMEOUT", "30"))

# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

WorkerName = Literal[
    "data_profile_worker",
    "metadata_worker",
    "data_modeling_worker",
    "data_quality_worker",
    "semantical_worker",
    "FINISH",
]


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    next_worker: str         # set by the planner; drives conditional routing
    current_task: str        # the specific task instruction sent to the active worker


# ---------------------------------------------------------------------------
# Planner routing schema
# ---------------------------------------------------------------------------


class PlannerDecision(BaseModel):
    reasoning: str
    next_worker: WorkerName
    task: str


# Derived from WorkerName to avoid duplication — strips out the "FINISH" sentinel.
_WORKER_NAMES: list[str] = [w for w in get_args(WorkerName) if w != "FINISH"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter_mcp_tools(all_tools: List[BaseTool], allowed_names: list[str]) -> List[BaseTool]:
    """Return only the MCP tools whose names appear in *allowed_names*."""
    allowed = set(allowed_names)
    return [t for t in all_tools if t.name in allowed]


def _build_fs_tools(write_extensions: list[str]) -> List[BaseTool]:
    """Return the filesystem tools for an agent (always includes read + list)."""
    tools: List[BaseTool] = [read_file, list_directory]
    if write_extensions:
        tools.append(make_write_tool(write_extensions))
    return tools


def _make_callback(agent_id: str) -> AuditTrailCallback:
    return AuditTrailCallback(log_path=AUDIT_LOG_PATH, agent_id=agent_id)


def _extract_planner_decision(content: str) -> dict:
    """Parse the JSON routing block from the planner's response."""
    # Try to extract a JSON block (with or without markdown fences)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        match = re.search(r"(\{[^{}]*\"next_worker\"[^{}]*\})", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: look for next_worker key anywhere
    nw_match = re.search(r'"next_worker"\s*:\s*"([^"]+)"', content)
    task_match = re.search(r'"task"\s*:\s*"([^"]+)"', content)
    return {
        "next_worker": nw_match.group(1) if nw_match else "FINISH",
        "task": task_match.group(1) if task_match else content,
        "reasoning": "",
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


async def build_graph(mcp_tools: List[BaseTool]):
    """Construct and return the compiled LangGraph graph.

    *mcp_tools* is the full list of tools loaded from the MCP servers.
    Each node filters this list to its allowed subset.
    """
    llm = init_chat_model(LLM_MODEL, temperature=LLM_TEMPERATURE)

    # -----------------------------------------------------------------------
    # Per-agent tool sets
    # -----------------------------------------------------------------------
    planner_tools = (
        _filter_mcp_tools(mcp_tools, PLANNER_MCP_TOOLS)
        + _build_fs_tools(PLANNER_FS_WRITE_EXTENSIONS)
    )
    profile_tools = (
        _filter_mcp_tools(mcp_tools, DATA_PROFILE_MCP_TOOLS)
        + _build_fs_tools(DATA_PROFILE_FS_WRITE_EXTENSIONS)
    )
    metadata_tools = (
        _filter_mcp_tools(mcp_tools, METADATA_MCP_TOOLS)
        + _build_fs_tools(METADATA_FS_WRITE_EXTENSIONS)
    )
    modeling_tools = (
        _filter_mcp_tools(mcp_tools, DATA_MODELING_MCP_TOOLS)
        + _build_fs_tools(DATA_MODELING_FS_WRITE_EXTENSIONS)
    )
    quality_tools = (
        _filter_mcp_tools(mcp_tools, DATA_QUALITY_MCP_TOOLS)
        + _build_fs_tools(DATA_QUALITY_FS_WRITE_EXTENSIONS)
    )
    semantical_tools = (
        _filter_mcp_tools(mcp_tools, SEMANTICAL_MCP_TOOLS)
        + _build_fs_tools(SEMANTICAL_FS_WRITE_EXTENSIONS)
    )

    # -----------------------------------------------------------------------
    # Planner node — supervisor that routes to workers
    # -----------------------------------------------------------------------

    planner_agent = create_react_agent(
        llm,
        planner_tools,
        state_modifier=PLANNER_SYSTEM_PROMPT,
    )

    async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
        cb = _make_callback("planner")
        cfg = {**config, "callbacks": [cb]}
        result = await planner_agent.ainvoke(
            {"messages": state["messages"]}, cfg
        )
        last_msg: AIMessage = result["messages"][-1]
        decision = _extract_planner_decision(str(last_msg.content))
        return {
            "messages": [last_msg],
            "next_worker": decision.get("next_worker", "FINISH"),
            "current_task": decision.get("task", ""),
        }

    # -----------------------------------------------------------------------
    # Worker node factory
    # -----------------------------------------------------------------------

    def _make_worker_node(agent_id: str, tools: List[BaseTool], system_prompt: str):
        worker_agent = create_react_agent(llm, tools, state_modifier=system_prompt)

        async def worker_node(state: AgentState, config: RunnableConfig) -> dict:
            cb = _make_callback(agent_id)
            cfg = {**config, "callbacks": [cb]}
            task_msg = HumanMessage(content=state["current_task"])
            result = await worker_agent.ainvoke({"messages": [task_msg]}, cfg)
            last: AIMessage = result["messages"][-1]
            summary = AIMessage(
                content=f"[{agent_id}] Task completed.\n\n{last.content}"
            )
            return {
                "messages": [summary],
                "next_worker": "planner",  # always return to planner
            }

        worker_node.__name__ = agent_id
        return worker_node

    # -----------------------------------------------------------------------
    # Build graph
    # -----------------------------------------------------------------------

    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node(
        "data_profile_worker",
        _make_worker_node("data_profile_worker", profile_tools, DATA_PROFILE_SYSTEM_PROMPT),
    )
    graph.add_node(
        "metadata_worker",
        _make_worker_node("metadata_worker", metadata_tools, METADATA_SYSTEM_PROMPT),
    )
    graph.add_node(
        "data_modeling_worker",
        _make_worker_node("data_modeling_worker", modeling_tools, DATA_MODELING_SYSTEM_PROMPT),
    )
    graph.add_node(
        "data_quality_worker",
        _make_worker_node("data_quality_worker", quality_tools, DATA_QUALITY_SYSTEM_PROMPT),
    )
    graph.add_node(
        "semantical_worker",
        _make_worker_node("semantical_worker", semantical_tools, SEMANTICAL_SYSTEM_PROMPT),
    )

    # Entry point
    graph.add_edge(START, "planner")

    # Routing from planner
    def _route(state: AgentState) -> str:
        nw = state.get("next_worker", "FINISH")
        return END if nw == "FINISH" else nw

    graph.add_conditional_edges(
        "planner",
        _route,
        {
            "data_profile_worker": "data_profile_worker",
            "metadata_worker": "metadata_worker",
            "data_modeling_worker": "data_modeling_worker",
            "data_quality_worker": "data_quality_worker",
            "semantical_worker": "semantical_worker",
            END: END,
        },
    )

    # All workers return to planner
    for worker in _WORKER_NAMES:
        graph.add_edge(worker, "planner")

    return graph.compile(checkpointer=None)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_pipeline(task: str) -> dict[str, Any]:
    """Start the MCP servers, build the graph, and run the pipeline.

    Parameters
    ----------
    task:
        Natural-language description of what the system should produce.

    Returns
    -------
    The final graph state dictionary.
    """
    mcp_server_config = {
        "duckdb": {
            "command": PYTHON_EXECUTABLE,
            "args": [MCP_DUCKDB_SERVER],
            "transport": "stdio",
            "env": {**os.environ, "DUCKDB_PATH": DUCKDB_PATH},
        },
        "dbt": {
            "command": MCP_DBT_SERVER,
            "args": [],
            "transport": "stdio",
            "env": {
                **os.environ,
                "DBT_PROJECT_DIR": DBT_PROJECT_DIR,
                "DBT_PROFILES_DIR": DBT_PROFILES_DIR,
            },
        },
    }

    # langchain-mcp-adapters >=0.1.0 removed the async context manager API.
    # The new pattern is: instantiate the client, then await client.get_tools()
    # which starts the MCP servers and returns bound tool objects.  The client
    # must remain in scope for the duration of the pipeline run so that the
    # server connections stay alive when agents call tools.
    client = MultiServerMCPClient(mcp_server_config)

    try:
        async with asyncio.timeout(MCP_STARTUP_TIMEOUT):
            mcp_tools: List[BaseTool] = await client.get_tools()
    except TimeoutError:
        raise RuntimeError(
            f"MCP servers did not start within {MCP_STARTUP_TIMEOUT}s. "
            "Check that the project venv exists and DUCKDB_PATH / DBT_PROJECT_DIR are correct."
        )

    compiled = await build_graph(mcp_tools)
    initial_state: AgentState = {
        "messages": [HumanMessage(content=task)],
        "next_worker": "",
        "current_task": task,
    }
    return await compiled.ainvoke(
        initial_state,
        {"recursion_limit": MAX_GRAPH_ITERATIONS},
    )
