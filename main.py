#!/usr/bin/env python3
"""Entry point for the Agentic AI Data Management pipeline.

Usage
-----
    python main.py
    python main.py "Custom task description"
    python main.py path/to/task.pdf
    python main.py path/to/task.txt
    python main.py "Preamble / context note." path/to/task.pdf

Each positional argument is either a plain-text string or a file path
(.pdf, .txt, .md). All parts are joined in order and sent as a single
task to the pipeline, so you can prepend context to a PDF spec:

    python main.py "The AzureSQL DB in the PDF has been migrated to the
    DuckDB warehouse the system has access to." case_study.pdf

The PIPELINE_TASK environment variable takes precedence over all
positional arguments. If nothing is supplied, the default
inspect-and-report task is used.
"""

import asyncio
import os
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


def _read_task_file(path: Path) -> str:
    """Extract text from a .pdf, .txt, or .md file to use as the pipeline task."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise SystemExit(
                "pypdf is required to read PDF task files.\n"
                "Install it with: uv pip install pypdf"
            )
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()
    else:
        return path.read_text(encoding="utf-8").strip()


def _resolve_arg(arg: str) -> str:
    """Return file contents if *arg* is an existing file path, otherwise return *arg* as-is."""
    candidate = Path(arg)
    if candidate.exists() and candidate.is_file():
        print(f"Reading task from file: {candidate}")
        return _read_task_file(candidate)
    return arg


async def main() -> None:
    env_task = os.getenv("PIPELINE_TASK")

    if env_task:
        task = env_task
    elif len(sys.argv) > 1:
        # Each argument is resolved independently (string or file path) then joined.
        parts = [_resolve_arg(a) for a in sys.argv[1:]]
        task = "\n\n".join(p for p in parts if p)
    else:
        task = _DEFAULT_TASK

    print("=" * 72)
    print("Agentic AI Data Management Pipeline")
    print("=" * 72)
    print(f"Task:\n{task}\n")
    print(f"Audit log  : {AUDIT_LOG_PATH}")
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
