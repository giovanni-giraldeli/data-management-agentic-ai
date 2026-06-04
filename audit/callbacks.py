"""LangGraph callbacks that produce a structured JSON audit trail.

Every agent interaction is appended to a JSON array file.  Each entry records:
  - timestamp      : UTC ISO-8601
  - agent_id       : which agent produced this event
  - event_type     : one of llm_start | llm_end | tool_start | tool_end |
                     chain_start | chain_end | llm_error | tool_error
  - inputs         : prompt strings (llm_start) or chain inputs (chain_start)
  - outputs        : generated text (llm_end) or chain outputs (chain_end)
  - tool_name      : present on tool_start / tool_end events
  - tool_input     : present on tool_start events
  - tool_output    : present on tool_end events
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class AuditTrailCallback(BaseCallbackHandler):
    """Thread-safe callback handler that appends entries to a JSON array file."""

    def __init__(self, log_path: str, agent_id: str) -> None:
        super().__init__()
        self.log_path = Path(log_path)
        self.agent_id = agent_id
        self._lock = threading.Lock()
        # Ensure the file exists and is a valid JSON array
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text("[]", encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, entry: Dict[str, Any]) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        entry["agent_id"] = self.agent_id
        with self._lock:
            try:
                log: list = json.loads(self.log_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, FileNotFoundError):
                log = []
            log.append(entry)
            self.log_path.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")

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

    # ------------------------------------------------------------------
    # Chain events
    # ------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._append({"event_type": "chain_start", "inputs": inputs})

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._append({"event_type": "chain_end", "outputs": outputs})
