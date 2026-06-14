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

Phase 2 injection
-----------------
After each worker completes, ``planner_node`` injects a ``[PHASE 2 REMINDER]``
``HumanMessage`` into the message list before invoking the Planner agent.  The
reminder includes the current plan and explicitly names the next required step
(first plan entry without "DONE") to prevent the Planner from skipping steps.

Worker quality review
---------------------
``planner_node`` tracks how many times each worker has been re-delegated to via
``retry_counts`` in ``AgentState``.  Escalating warnings are injected at count == 1
(advisory) and count >= 2 (hard block) to enforce the re-delegation cap.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Annotated, Any, List, Literal, get_args

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
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

# Maximum steps for the Planner's internal ReAct loop per invocation.
PLANNER_MAX_STEPS: int = int(os.getenv("PLANNER_MAX_STEPS", "50"))

# Seconds to wait for both MCP servers to finish starting up.
MCP_STARTUP_TIMEOUT: float = float(os.getenv("MCP_STARTUP_TIMEOUT", "30"))

# Marker written at the start of every worker completion message.
# planner_node detects this to know it is in Phase 2.
_WORKER_COMPLETION_MARKER = "] Task completed."

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
    plan: list[str]          # numbered plan maintained by the Planner across steps
    retry_counts: dict[str, int]  # how many times each worker has been re-delegated to


# ---------------------------------------------------------------------------
# Planner routing schema
# ---------------------------------------------------------------------------


class PlannerDecision(BaseModel):
    reasoning: str
    next_worker: WorkerName
    task: str
    plan: list[str] | None = None  # only present when the Planner revises the plan


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


def _make_callback(agent_id: str, session_id: str) -> AuditTrailCallback:
    return AuditTrailCallback(log_path=AUDIT_LOG_PATH, agent_id=agent_id, session_id=session_id)


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
    raw_nw = nw_match.group(1) if nw_match else "FINISH"

    # Validate: if the LLM returned an unrecognised worker name, default to FINISH
    # rather than letting an unknown string reach LangGraph's edge mapping (KeyError).
    _valid = set(get_args(WorkerName))
    if raw_nw not in _valid:
        raw_nw = "FINISH"

    return {
        "next_worker": raw_nw,
        "task": task_match.group(1) if task_match else content,
        "reasoning": "",
    }


def _find_next_plan_step(
    plan: list[str], completed_worker: str | None
) -> str:
    """Return a hint string naming the next non-DONE plan step.

    Scans forward past the first non-DONE step that mentions *completed_worker*
    (the step that was just finished), then returns the text of the following step.
    If *completed_worker* is None (Phase 1 → Phase 2 transition), returns the first
    non-DONE step unconditionally.
    """
    if not plan:
        return ""

    past_completed = completed_worker is None

    for i, step in enumerate(plan):
        if "DONE" in step.upper():
            continue
        if not past_completed and completed_worker and completed_worker in step:
            past_completed = True
            continue
        if past_completed:
            return (
                f"\n\nThe NEXT required step in your plan is:\n"
                f"  Step {i + 1}: {step}\n"
                "You MUST delegate to this step. "
                "Do NOT skip ahead or re-survey the project."
            )

    return ""  # all steps done or no match found


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


async def build_graph(mcp_tools: List[BaseTool], session_id: str):
    """Construct and return the compiled LangGraph graph.

    *mcp_tools* is the full list of tools loaded from the MCP servers.
    Each node filters this list to its allowed subset.
    """
    # LangChain 1.x requires model_provider to be passed explicitly rather
    # than inferred from a "provider/model" string.  Split on "/" so both
    # formats work: "google_genai/gemini-2.5-flash" (recommended)
    # and bare model names like "gpt-4o" (provider inferred by LangChain).
    if "/" in LLM_MODEL:
        _provider, _model_name = LLM_MODEL.split("/", 1)
        llm = init_chat_model(_model_name, model_provider=_provider, temperature=LLM_TEMPERATURE)
    else:
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
        prompt=PLANNER_SYSTEM_PROMPT,
    )

    async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
        cb = _make_callback("planner", session_id)
        cfg = {**config, "callbacks": [cb]}

        messages = list(state["messages"])
        last_msg = messages[-1] if messages else None

        # Detect Phase 2: the last message is a worker completion HumanMessage.
        is_phase_2 = (
            isinstance(last_msg, HumanMessage)
            and _WORKER_COMPLETION_MARKER in (last_msg.content or "")
        )

        # Extract which worker just completed.
        completed_worker: str | None = None
        if is_phase_2 and last_msg is not None:
            m = re.match(r"\[([^\]]+)\] Task completed\.", last_msg.content or "")
            if m:
                completed_worker = m.group(1)

        # Retry tracking.
        current_retry_counts: dict[str, int] = dict(state.get("retry_counts") or {})
        worker_retry_count = (
            current_retry_counts.get(completed_worker, 0) if completed_worker else 0
        )
        if worker_retry_count == 1:
            retry_note = (
                f"\n\n⚠ NOTE: {completed_worker} has already been retried once. "
                "If the output is still incomplete, note the remaining gap as an "
                "outstanding item and advance to the next plan step — "
                "do not re-delegate a third time."
            )
        elif worker_retry_count >= 2:
            retry_note = (
                f"\n\n🚫 HARD LIMIT: {completed_worker} has been retried "
                f"{worker_retry_count} time(s). You MUST NOT re-delegate to this "
                "worker again. Accept the output as-is, note any remaining gaps "
                "in the task field, and advance to the next plan step."
            )
        else:
            retry_note = ""

        # Inject Phase 2 reminder with explicit next-step guidance.
        plan_list: list[str] = list(state.get("plan") or [])
        if is_phase_2 and plan_list:
            plan_text = "\n".join(plan_list)
            next_step_hint = _find_next_plan_step(plan_list, completed_worker)
            messages = messages + [
                HumanMessage(
                    content=(
                        "[PHASE 2 REMINDER]\n"
                        "The worker above has just finished. Your current plan is:\n\n"
                        f"{plan_text}\n\n"
                        "Review the worker's summary against the expected deliverables "
                        "(see 'Worker output review' in your instructions).\n"
                        "  • If acceptable: mark the completed step DONE in the plan "
                        "and output the routing JSON for the next step.\n"
                        "  • If a deliverable is missing: re-delegate to the SAME "
                        "worker with a corrective task describing exactly what is missing.\n"
                        "You may make AT MOST 2 targeted verification calls before "
                        "routing (e.g. confirm a model was materialised, read a "
                        "specific output file). After those calls — or immediately "
                        "if the summary is sufficient — write the JSON block.\n"
                        "⚠ NO open-ended re-survey: do not loop through directories, "
                        "do not cycle dbt list resource_types, do not re-read files "
                        "already in this conversation. Workers are not function calls "
                        f"— delegate only through the JSON routing block."
                        f"{next_step_hint}{retry_note}"
                    )
                )
            ]

        result = await planner_agent.ainvoke(
            {"messages": messages},
            {**cfg, "recursion_limit": PLANNER_MAX_STEPS},
        )
        last_ai_msg: AIMessage = result["messages"][-1]
        decision = _extract_planner_decision(str(last_ai_msg.content))

        # Keep the plan up to date: use the revised plan if the Planner provided one.
        new_plan: list[str] = decision.get("plan") or plan_list

        # Track retries: if the Planner re-delegates to the worker that just ran,
        # increment its retry counter.
        next_w = decision.get("next_worker", "FINISH")
        if completed_worker and next_w == completed_worker and next_w in _WORKER_NAMES:
            current_retry_counts[next_w] = current_retry_counts.get(next_w, 0) + 1

        return {
            "messages": [last_ai_msg],
            "next_worker": next_w,
            "current_task": decision.get("task", ""),
            "plan": new_plan,
            "retry_counts": current_retry_counts,
        }

    # -----------------------------------------------------------------------
    # Worker node factory
    # -----------------------------------------------------------------------

    def _make_worker_node(agent_id: str, tools: List[BaseTool], system_prompt: str):
        worker_agent = create_react_agent(llm, tools, prompt=system_prompt)

        async def worker_node(state: AgentState, config: RunnableConfig) -> dict:
            cb = _make_callback(agent_id, session_id)
            cfg = {**config, "callbacks": [cb]}
            task_msg = HumanMessage(content=state["current_task"])
            result = await worker_agent.ainvoke({"messages": [task_msg]}, cfg)
            last: AIMessage = result["messages"][-1]
            # HumanMessage so planner_node can detect Phase 2 via _WORKER_COMPLETION_MARKER.
            summary = HumanMessage(
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
        # Treat any unrecognised value (e.g. LLM hallucination) as FINISH.
        if nw not in _WORKER_NAMES:
            return END
        return nw

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

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_pipeline(task: str) -> tuple[dict[str, Any], str]:
    """Start the MCP servers, build the graph, and run the pipeline.

    Parameters
    ----------
    task:
        Natural-language description of what the system should produce.

    Returns
    -------
    A tuple of (final graph state dict, session_id string).
    """
    session_id = str(uuid.uuid4())

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

    compiled = await build_graph(mcp_tools, session_id)
    initial_state: AgentState = {
        "messages": [HumanMessage(content=task)],
        "next_worker": "",
        "current_task": task,
        "plan": [],
        "retry_counts": {},
    }
    result = await compiled.ainvoke(
        initial_state,
        {"recursion_limit": MAX_GRAPH_ITERATIONS},
    )
    return result, session_id
