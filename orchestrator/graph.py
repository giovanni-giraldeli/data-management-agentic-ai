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
from typing import Annotated, Any, List, Literal, get_args
from uuid import uuid4

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, create_react_agent
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
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_RPM_LIMIT,
    LLM_TEMPERATURE,
    MCP_DBT_SERVER,
    MCP_DUCKDB_SERVER,
    PLANNER_MAX_STEPS,
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
    plan: list[str]          # the Planner's current execution plan (steps as strings)
    retry_counts: dict[str, int]  # how many times each worker has been re-delegated to


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


def _find_next_plan_step(plan: list[str], completed_worker: str | None) -> str | None:
    """Return explicit hint text naming the first non-DONE plan step.

    Scans forward from the step that mentions *completed_worker* (or from the
    top if no match is found) and returns the first step not yet marked DONE.
    Returns None when the plan is empty or all steps are done.
    """
    if not plan:
        return None

    # Find the index of the step that references the completed worker so we
    # look for the *next* step after it, not the same one again.
    start_idx = 0
    if completed_worker:
        for i, step in enumerate(plan):
            if completed_worker in step and "DONE" in step.upper():
                start_idx = i + 1
                break

    for i in range(start_idx, len(plan)):
        step = plan[i]
        if "DONE" not in step.upper():
            return (
                f"\n\nThe NEXT required step in your plan is:\n"
                f"  Step {i + 1}: {step}\n"
                "You MUST delegate to this step. "
                "Do NOT skip ahead or re-survey the project."
            )

    return None


# ---------------------------------------------------------------------------
# Deduplicating ToolNode — prevents Planner exploration loops
# ---------------------------------------------------------------------------

# Filesystem tools whose results are static within one pipeline run: calling
# list_directory or read_file on the same path twice can never yield new
# information.  We deduplicate these calls so that an exact repeat is blocked
# and the LLM receives a clear "you already have this — write your plan"
# message instead of silently re-executing and looping forever.
#
# Database / dbt tools (dbt list, duckdb_list_tables, …) are NOT deduplicated
# because their results change during the pipeline as workers materialise models.
# "list" (dbt list MCP tool) is also deduplicated within a single Planner
# invocation — calling `dbt list --resource-type model` and then cycling through
# every other resource_type after receiving "OK" results adds no information.
# Note: _seen is RESET at the start of each planner_node call (see below), so
# dedup is per-invocation only.  After a worker runs the Planner is allowed to
# call dbt list again (e.g. to confirm newly materialised models exist).
_DEDUP_TOOL_NAMES: frozenset[str] = frozenset({"read_file", "list_directory", "list"})


class _DeduplicatingToolNode(ToolNode):
    """ToolNode that blocks exact-duplicate Planner tool calls within one invocation.

    On the first call to read_file, list_directory, or list (dbt list) with a
    given set of arguments, the tool executes normally and the key is cached in
    _seen.  Any subsequent call with the *identical* (tool_name, args) pair
    returns an error-style ToolMessage telling the LLM it already has the result
    and should stop exploring and write its plan.

    _seen is cleared at the start of each planner_node call so deduplication is
    per-Planner-invocation, not per-pipeline-run.  This allows the Planner to
    call dbt list again after a worker returns (e.g. to verify new models), while
    still blocking endless cycling through every resource_type in a single Phase.
    """

    def __init__(self, tools: list, **kwargs) -> None:
        super().__init__(tools, **kwargs)
        self._seen: set[str] = set()

    def _call_key(self, tc: dict) -> str:
        return json.dumps(
            {"name": tc["name"], "args": tc.get("args", {})},
            sort_keys=True,
            default=str,
        )

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: ANN401
        messages = input.get("messages", []) if isinstance(input, dict) else list(input)
        if not messages:
            return await super().ainvoke(input, config, **kwargs)

        last = messages[-1]
        tool_calls: list[dict] = getattr(last, "tool_calls", None) or []

        blocked: list[ToolMessage] = []
        new_calls: list[dict] = []

        for tc in tool_calls:
            if tc["name"] not in _DEDUP_TOOL_NAMES:
                new_calls.append(tc)
                continue
            key = self._call_key(tc)
            if key in self._seen:
                blocked.append(
                    ToolMessage(
                        content=(
                            f"[DUPLICATE CALL BLOCKED] You already called "
                            f"'{tc['name']}' with these exact parameters earlier "
                            "in this session and the result will not change. "
                            "You have enough information — stop exploring and "
                            "write your plan JSON now."
                        ),
                        tool_call_id=tc["id"],
                        status="error",
                    )
                )
            else:
                self._seen.add(key)
                new_calls.append(tc)

        # All calls were duplicates — return the blocked messages directly.
        if not new_calls:
            return {"messages": blocked}

        # No duplicates — normal execution.
        if not blocked:
            return await super().ainvoke(input, config, **kwargs)

        # Mixed: run the new calls normally, then append the blocked messages.
        modified = last.model_copy(update={"tool_calls": new_calls})
        modified_input = (
            {**input, "messages": messages[:-1] + [modified]}
            if isinstance(input, dict)
            else messages[:-1] + [modified]
        )
        result = await super().ainvoke(modified_input, config, **kwargs)
        result_msgs = result.get("messages", []) if isinstance(result, dict) else list(result)
        return {"messages": result_msgs + blocked}


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
    _llm_kwargs: dict = {"temperature": LLM_TEMPERATURE}
    if LLM_MAX_TOKENS is not None:
        _llm_kwargs["max_tokens"] = LLM_MAX_TOKENS
    # Proactive rate limiting: queue requests before they reach the API so the
    # pipeline never triggers a 429.  All six agents share one LLM instance, so
    # a single limiter here covers the entire pipeline.
    # Set LLM_RPM_LIMIT in .env to match your API tier (e.g. 15 for the Gemini
    # AI Studio free tier).  0 = unlimited (default).
    if LLM_RPM_LIMIT > 0:
        from langchain_core.rate_limiters import InMemoryRateLimiter
        _llm_kwargs["rate_limiter"] = InMemoryRateLimiter(
            requests_per_second=LLM_RPM_LIMIT / 60,
            check_every_n_seconds=0.1,
            max_bucket_size=1,  # no bursting — enforce the rate strictly
        )
    if "/" in LLM_MODEL:
        _provider, _model_name = LLM_MODEL.split("/", 1)
        llm = init_chat_model(_model_name, model_provider=_provider, **_llm_kwargs)
    else:
        llm = init_chat_model(LLM_MODEL, **_llm_kwargs)

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

    # The Planner uses a _DeduplicatingToolNode which:
    #   1. Blocks exact-duplicate read_file / list_directory / dbt-list calls within
    #      a single Planner invocation.  _seen is cleared at the start of each
    #      planner_node call so dedup is per-invocation, not per-pipeline-run.
    #      This prevents the Planner from cycling through the same filesystem paths
    #      or through every dbt resource_type endlessly during Phase 1 exploration.
    #   2. Handles tool errors gracefully (handle_tool_errors=True) so exceptions
    #      such as FileNotFoundError from get_lineage_dev are returned as ToolMessages
    #      instead of crashing the pipeline.
    # Workers use a plain ToolNode with error handling only — deduplication is not
    # needed there because workers execute a focused task, not open-ended exploration.
    planner_dedup_node = _DeduplicatingToolNode(planner_tools, handle_tool_errors=True)
    planner_agent = create_react_agent(
        llm,
        planner_dedup_node,
        prompt=PLANNER_SYSTEM_PROMPT,
    )

    # Worker-name sentinel used for Phase 2 detection.
    _WORKER_COMPLETION_MARKER = "] Task completed."

    async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
        cb = _make_callback("planner", session_id)
        # Override the outer graph's recursion_limit so the Planner's inner
        # ReAct agent cannot spin indefinitely.  Each tool call costs 2 steps
        # (one LLM step + one tool-execution step), so PLANNER_MAX_STEPS=25
        # allows ~12 tool calls before GraphRecursionError is raised.
        cfg = {**config, "callbacks": [cb], "recursion_limit": PLANNER_MAX_STEPS}

        # Reset the dedup cache for this invocation.  Deduplication is
        # per-planner-call, not per-pipeline-run: within a single exploration
        # phase the Planner cannot repeat a tool call; but after a worker
        # returns the Planner is allowed to call dbt list / list_directory
        # again (e.g. to confirm newly materialised models exist).
        planner_dedup_node._seen.clear()

        # ------------------------------------------------------------------
        # Phase 2 detection and context injection.
        #
        # After a worker completes, its summary arrives as a HumanMessage
        # in the format "[worker_name] Task completed.\n\n<summary>".
        # We detect this, extract the worker name for retry tracking, and
        # inject a [PHASE 2 REMINDER] that:
        #   - Echoes the current plan so the Planner can identify the next step.
        #   - Instructs the Planner to evaluate the summary and route immediately.
        #   - Escalates the retry warning if the worker has already been retried.
        #   - Names the explicit next required step to prevent silent skipping.
        # ------------------------------------------------------------------
        messages = list(state["messages"])
        last_msg = messages[-1] if messages else None
        is_phase_2 = (
            isinstance(last_msg, HumanMessage)
            and _WORKER_COMPLETION_MARKER in (last_msg.content or "")
        )

        # Extract the name of the worker that just completed (e.g. "data_profile_worker").
        completed_worker: str | None = None
        if is_phase_2 and last_msg is not None:
            m = re.match(r"\[([^\]]+)\] Task completed\.", last_msg.content or "")
            if m:
                completed_worker = m.group(1)

        # Current retry tally (carried forward in state across planner calls).
        current_retry_counts: dict[str, int] = dict(state.get("retry_counts") or {})
        worker_retry_count = (
            current_retry_counts.get(completed_worker, 0) if completed_worker else 0
        )

        # Build an escalating retry note to include in the reminder.
        if worker_retry_count == 1:
            retry_note = (
                f"\n⚠ NOTE: {completed_worker} has already been retried once. "
                "If the output is still incomplete, note the remaining gap as an "
                "outstanding item and advance to the next plan step — "
                "do not re-delegate a third time."
            )
        elif worker_retry_count >= 2:
            retry_note = (
                f"\n🚫 HARD LIMIT: {completed_worker} has been retried "
                f"{worker_retry_count} time(s). You MUST NOT re-delegate to this "
                "worker again. Accept the output as-is, note any remaining gaps "
                "in the task field, and advance to the next plan step."
            )
        else:
            retry_note = ""

        if is_phase_2 and state.get("plan"):
            plan_text = "\n".join(state["plan"])
            next_step_hint = _find_next_plan_step(state["plan"], completed_worker)
            messages.append(
                HumanMessage(
                    content=(
                        "[PHASE 2 REMINDER]\n"
                        "The worker above has just finished. Your current plan is:\n\n"
                        f"{plan_text}\n\n"
                        "Review the worker's summary against the expected deliverables "
                        "(see 'Worker output review' in your instructions).\n"
                        "  • If acceptable: output the routing JSON for the NEXT step.\n"
                        "  • If a deliverable is missing: re-delegate to the SAME worker "
                        "with a corrective task describing exactly what is missing.\n"
                        "You may make AT MOST 2 targeted verification calls before "
                        "routing (e.g. confirm a model was materialised, read a "
                        "specific output file). After those calls — or immediately "
                        "if the summary is sufficient — write the JSON block.\n"
                        "⚠ NO open-ended re-survey: do not loop through directories, "
                        "do not cycle dbt list resource_types, do not re-read files "
                        "already in this conversation. Workers are not function calls "
                        f"— delegate only through the JSON routing block.{retry_note}"
                        f"{next_step_hint or ''}"
                    )
                )
            )

        try:
            result = await planner_agent.ainvoke(
                {"messages": messages}, cfg
            )
            last_msg: AIMessage = result["messages"][-1]
        except Exception as exc:
            # GraphRecursionError (or any unexpected error) from the inner agent:
            # produce a FINISH so the outer graph terminates cleanly rather than
            # crashing.  The error is surfaced in the final summary.
            if "recursion" in type(exc).__name__.lower() or "recursion" in str(exc).lower():
                reason = (
                    "The Planner exceeded its exploration budget without reaching a "
                    "decision. This usually means the project has no dbt models yet "
                    "(dbt list returned 'OK') and the Planner kept searching instead "
                    "of delegating. Re-run with a more specific task or check the "
                    "dbt project structure."
                )
            else:
                reason = f"Unexpected Planner error: {exc}"
            last_msg = AIMessage(content=json.dumps({
                "reasoning": reason,
                "next_worker": "FINISH",
                "task": reason,
            }))
        decision = _extract_planner_decision(str(last_msg.content))

        # ------------------------------------------------------------------
        # Retry tracking — if the Planner routes back to the worker that just
        # completed, record it so that escalating warnings can be shown on the
        # next invocation and a hard cap can be enforced after two retries.
        # ------------------------------------------------------------------
        next_w = decision.get("next_worker", "FINISH")
        if completed_worker and next_w == completed_worker and next_w in _WORKER_NAMES:
            current_retry_counts[next_w] = current_retry_counts.get(next_w, 0) + 1

        # Carry the plan forward in state.  The Planner includes "plan" in its
        # JSON on the first response and whenever it revises the plan; it omits
        # the field on routine step-by-step execution to save tokens.  We keep
        # the last known plan so it is always visible in the graph state.
        updated_plan = decision.get("plan")
        if isinstance(updated_plan, list) and updated_plan:
            new_plan = updated_plan
        else:
            new_plan = state.get("plan", [])

        return {
            "messages": [last_msg],
            "next_worker": next_w,
            "current_task": decision.get("task", ""),
            "plan": new_plan,
            "retry_counts": current_retry_counts,
        }

    # -----------------------------------------------------------------------
    # Worker node factory
    # -----------------------------------------------------------------------

    def _make_worker_node(agent_id: str, tools: List[BaseTool], system_prompt: str):
        worker_agent = create_react_agent(
            llm,
            ToolNode(tools, handle_tool_errors=True),
            prompt=system_prompt,
        )

        async def worker_node(state: AgentState, config: RunnableConfig) -> dict:
            cb = _make_callback(agent_id, session_id)
            cfg = {**config, "callbacks": [cb]}
            task_msg = HumanMessage(content=state["current_task"])
            result = await worker_agent.ainvoke({"messages": [task_msg]}, cfg)
            last: AIMessage = result["messages"][-1]
            # Return the worker summary as a HumanMessage, not an AIMessage.
            # The Planner is a create_react_agent whose conversation history
            # accumulates across the pipeline: each call sees all prior messages.
            # If the worker summary were an AIMessage the Planner would see two
            # consecutive AI turns (its own routing decision + the worker report)
            # and interpret the worker summary as its own prior response — causing
            # it to produce an empty completion on the next call.
            # Using HumanMessage preserves the correct Human→AI alternation:
            #   Human(task) → AI(plan+delegate) → Human(worker report) → AI(next step)
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
    A tuple of (final graph state dict, session_id).  The session_id
    identifies this run's entries in the audit log.
    """
    session_id = str(uuid4())

    # Write the very first audit entry for this session so that the user's
    # prompt is recorded before any agent activity begins.
    AuditTrailCallback(
        log_path=AUDIT_LOG_PATH, agent_id="system", session_id=session_id
    ).log_system_start(task)

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
                # Disable all dbt Cloud features so the server runs in local
                # CLI-only mode without requiring DBT_HOST / DBT_TOKEN.
                "DISABLE_DISCOVERY": "true",
                "DISABLE_SEMANTIC_LAYER": "true",
                "DISABLE_ADMIN_API": "true",
                "DISABLE_SQL": "true",
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
        "plan": [],          # populated by the Planner on its first response
        "retry_counts": {},  # incremented each time Planner re-delegates to a worker
    }
    final_state = await compiled.ainvoke(
        initial_state,
        {"recursion_limit": MAX_GRAPH_ITERATIONS},
    )
    return final_state, session_id
