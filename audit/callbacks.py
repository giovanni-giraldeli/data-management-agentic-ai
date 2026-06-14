"""LangGraph callbacks that produce a structured JSON Lines audit trail.

Every agent interaction is appended to ``audit_trail.jsonl`` (one JSON object
per line).  Each entry records:

  Fields present on every entry (in this order):
  - session_id     : UUID generated once per pipeline run; groups all entries
                     from the same invocation so multiple runs in the same file
                     can be filtered independently
  - timestamp      : UTC ISO-8601
  - agent_id       : which agent produced this event
  - event_type     : one of system_start | system_cancelled | llm_start |
                     llm_end | tool_start | tool_end | llm_error | tool_error

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

    def log_system_cancelled(self) -> None:
        """Write a system_cancelled entry when the user interrupts the pipeline.

        Called from main.py on KeyboardInterrupt so that every session in the
        audit log has a clear terminal event — either system_start … FINISH or
        system_start … system_cancelled.
        """
        self._append({"event_type": "system_cancelled"})

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
        # Log only the message count, not the full prompt list.
        # In a ReAct agent every LLM call receives the entire accumulated
        # conversation history, so logging `prompts` in full causes the audit
        # file to grow quadratically: each successive entry re-copies the system
        # prompt plus every prior tool call and result.  The actual content is
        # already captured by system_start, tool_start, tool_end, and llm_end
        # events, so storing it again here adds no information and dominates the
        # log size.  message_count is kept for context-window tracking.
        self._append({"event_type": "llm_start", "message_count": len(prompts)})

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        # For chat models (ChatGeneration), gen.text is empty when the response
        # is a list-of-parts (Gemini's default format) or a pure tool-call.
        # The actual content lives in gen.message.content.  We extract it here
        # so the audit log contains the Planner's reasoning and routing JSON.
        # When the LLM called a tool instead of writing text, we log the tool
        # name(s) so the entry is still informative rather than just "".
        outputs = []
        for gens in response.generations:
            for gen in gens:
                text = ""
                if hasattr(gen, "message"):
                    msg = gen.message
                    content = getattr(msg, "content", "")
                    if isinstance(content, list):
                        # Multi-part Gemini response: join text parts
                        text = "\n".join(
                            part.get("text", "")
                            for part in content
                            if isinstance(part, dict) and part.get("type") == "text"
                        ).strip()
                    elif isinstance(content, str):
                        text = content.strip()
                    # If still empty the response was a pure tool-call — surface
                    # the tool name(s) so the audit entry is meaningful.
                    if not text:
                        tool_calls = getattr(msg, "tool_calls", [])
                        if tool_calls:
                            names = ", ".join(
                                tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                                for tc in tool_calls
                            )
                            text = f"[tool_call: {names}]"
                # Fall back to gen.text for non-chat models
                if not text:
                    text = getattr(gen, "text", "") or ""
                outputs.append(text)
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
        # `output` is a LangChain ToolMessage object.  str(output) produces a
        # verbose wrapper including content list, name, tool_call_id, and
        # artifact fields.  Extract just the plain-text result string so the
        # audit entry stays compact and human-readable.
        if hasattr(output, "content"):
            content = output.content
            if isinstance(content, list):
                # content=[{'type': 'text', 'text': '...'}, ...]
                text = " ".join(
                    part.get("text", str(part))
                    for part in content
                    if isinstance(part, dict)
                )
            else:
                text = str(content)
        else:
            text = str(output)
        self._append({"event_type": "tool_end", "tool_output": text})

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
