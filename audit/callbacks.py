"""LangGraph callbacks that produce a structured JSON Lines audit trail.

Every agent interaction is appended to ``audit_trail.jsonl`` (one JSON object
per line).  Each entry records:

  Fields present on every entry (in this order):
  - session_id     : UUID generated once per pipeline run; groups all entries
                     from the same invocation so multiple runs in the same file
                     can be filtered independently
  - timestamp      : UTC ISO-8601
  - agent_id       : which agent produced this event
  - event_type     : one of system_start | llm_start | llm_end | tool_start |
                     tool_end | llm_error | tool_error

  Event-specific fields:
  - prompt         : user task string (system_start only)
  - inputs         : prompt strings (llm_start)
  - outputs        : generated text (llm_end)
  - tool_name      : present on tool_start / tool_end events
  - tool_input     : present on tool_start events
  - tool_output    : present on tool_end events

JSON Lines format (one entry per line) is used instead of a JSON array so that
concurrent agent callbacks can append safely without reading the whole file
first.  The threading lock prevents interleaved writes within one process.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID, uuid4

# BaseCallbackHandler is deprecated in LangChain 1.x in favour of astream_events,
# but it has not been removed and continues to function correctly for audit purposes.
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class AuditTrailCallback(BaseCallbackHandler):
    """Thread-safe callback handler that appends entries to a JSON Lines file.

    Each call to ``_append`` acquires a process-level lock, serialises the
    entry to a single JSON line, and appends it.  No file-seek or full-read
    is required, making it safe for concurrent workers.
    """

    # Class-level lock shared across all instances so that agents running in
    # parallel threads cannot interleave their writes to the same file.
    _file_lock: threading.Lock = threading.Lock()

    def __init__(self, log_path: str, agent_id: str, session_id: str | None = None) -> None:
        super().__init__()
        self.log_path = Path(log_path)
        self.agent_id = agent_id
        # session_id groups all entries from one pipeline run so that
        # multiple runs appended to the same file can be queried separately.
        self.session_id: str = session_id or str(uuid4())
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _append(self, entry: Dict[str, Any]) -> None:
        # Build a new dict so that session_id is always the first key,
        # followed by timestamp and agent_id, then the event-specific fields.
        # Python 3.7+ dicts preserve insertion order, so this controls the
        # key order in the serialised JSON line.
        ordered: Dict[str, Any] = {
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
        }
        ordered.update(entry)
        line = json.dumps(ordered, default=str)
        with self._file_lock:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    # ------------------------------------------------------------------
    # System event (called once per session, before any agent runs)
    # ------------------------------------------------------------------

    def log_system_start(self, prompt: str) -> None:
        """Write a system_start entry that records the user's trigger prompt.

        This is the first entry for every session and lets analysts see
        what task was submitted without having to parse LLM input messages.
        """
        self._append({"event_type": "system_start", "prompt": prompt})

    # ------------------------------------------------------------------
    # LLM events
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._append({"event_type": "llm_start", "inputs": prompts})

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        outputs = [
            gen.text if hasattr(gen, "text") else str(gen)
            for gens in response.generations
            for gen in gens
        ]
        self._append({"event_type": "llm_end", "outputs": outputs})

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._append({"event_type": "llm_error", "error": str(error)})

    # ------------------------------------------------------------------
    # Tool events
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._append(
            {
                "event_type": "tool_start",
                "tool_name": serialized.get("name", "unknown_tool"),
                "tool_input": input_str,
            }
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._append({"event_type": "tool_end", "tool_output": str(output)})

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._append({"event_type": "tool_error", "error": str(error)})

    # Chain events are intentionally NOT logged.
    # In LangGraph 1.x, on_chain_start / on_chain_end fire at every level of the
    # nested execution hierarchy (outer graph, react-agent sub-graph, each internal
    # node, tool executor, …).  A single agent invocation produces dozens of chain
    # events that are not meaningful for audit purposes and inflate the log with
    # duplicates.  Only LLM and tool events are captured.
