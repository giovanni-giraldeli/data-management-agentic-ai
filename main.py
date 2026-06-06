#!/usr/bin/env python3
"""Entry point for the Agentic AI Data Management pipeline.

Usage
-----
    python main.py
    python main.py "Custom task description"

The pipeline task can also be set via the PIPELINE_TASK environment variable.
If neither is supplied, the default use-case task from the thesis is used.
"""

import asyncio
import sys
from pathlib import Path

# Make sure the repo root is on the path regardless of where this is invoked from
_REPO_ROOT = Path(__file__).parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv()

from config import AUDIT_LOG_PATH
from orchestrator.graph import run_pipeline

_DEFAULT_TASK = (
    "Inspect the current state of the project and report back. "
    "Specifically: "
    "(1) List all tables present in the DuckDB warehouse and summarise their row counts and columns. "
    "(2) List all existing dbt models, sources, and tests defined in the project. "
    "(3) Summarise any data profile reports (.md files) already written under docs/. "
    "Do not create, modify, or delete any files. Only read and report."
)


async def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_TASK
    import os
    task = os.getenv("PIPELINE_TASK", task)

    print("=" * 72)
    print("Agentic AI Data Management Pipeline")
    print("=" * 72)
    print(f"Task:\n{task}\n")
    print(f"Audit log: {AUDIT_LOG_PATH}")
    print("=" * 72)

    result = await run_pipeline(task)

    print("\n" + "=" * 72)
    print("Pipeline complete.")
    print("=" * 72)

    # Print the final planner summary (last AI message)
    messages = result.get("messages", [])
    for msg in reversed(messages):
        from langchain_core.messages import AIMessage
        if isinstance(msg, AIMessage):
            print("\nFinal summary:\n")
            print(msg.content)
            break

    print(f"\nFull audit trail written to: {AUDIT_LOG_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
