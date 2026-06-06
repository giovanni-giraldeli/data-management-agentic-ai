"""File-system tools for reading and writing dbt project files.

All paths accepted by these tools are **relative to the dbt project directory**.
Absolute paths and path-traversal attempts are rejected.

``make_write_tool`` is a factory that produces a write tool scoped to a specific
set of file extensions, enforcing the least-privilege access model defined in the
thesis for each agent.
"""

import os
from pathlib import Path
from typing import List

from langchain_core.tools import StructuredTool, tool

_DBT_PROJECT_DIR = Path(
    os.environ.get("DBT_PROJECT_DIR", Path(__file__).parent.parent / "agentic_dbt_project")
).resolve()

# Directories to skip when listing (dbt internals)
_SKIP_DIRS = {"target", "dbt_packages", ".git", "__pycache__"}


def _resolve_safe(relative_path: str) -> Path:
    """Resolve *relative_path* under the dbt project root, rejecting traversal."""
    resolved = (_DBT_PROJECT_DIR / relative_path).resolve()
    if not str(resolved).startswith(str(_DBT_PROJECT_DIR)):
        raise PermissionError(
            f"Access denied: '{relative_path}' resolves outside the dbt project directory."
        )
    return resolved


# ---------------------------------------------------------------------------
# Read-only tools (shared by all agents)
# ---------------------------------------------------------------------------


@tool
def read_file(path: str) -> str:
    """Read the text contents of a file inside the dbt project.

    Parameters
    ----------
    path:
        Path relative to the dbt project directory, e.g. ``models/source/src_aspnet.yml``.
    """
    try:
        resolved = _resolve_safe(path)
        if not resolved.exists():
            return f"File not found: {path}"
        if not resolved.is_file():
            return f"Not a file: {path}"
        return resolved.read_text(encoding="utf-8")
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR reading '{path}': {exc}"


@tool
def list_directory(path: str = "") -> str:
    """List all files recursively within a directory of the dbt project.

    Parameters
    ----------
    path:
        Path relative to the dbt project directory.  Leave empty to list the
        entire project tree (excluding dbt internals such as 'target/').
    """
    try:
        base = _resolve_safe(path) if path else _DBT_PROJECT_DIR
        if not base.exists():
            return f"Directory not found: {path!r}"
        items: List[str] = []
        for item in sorted(base.rglob("*")):
            # Skip internal dbt / Python artefacts
            if any(skip in item.parts for skip in _SKIP_DIRS):
                continue
            if item.is_file():
                items.append(str(item.relative_to(base)))
        return "\n".join(items) if items else "(empty)"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR listing '{path}': {exc}"


# ---------------------------------------------------------------------------
# Write tool factory – scoped per agent
# ---------------------------------------------------------------------------


def make_write_tool(allowed_extensions: List[str]) -> StructuredTool:
    """Return a ``write_file`` tool that only permits *allowed_extensions*.

    Parameters
    ----------
    allowed_extensions:
        List of permitted file extensions including the leading dot,
        e.g. ``['.md']`` or ``['.yml', '.sql']``.
    """
    allowed_set = {ext.lower() for ext in allowed_extensions}
    ext_label = ", ".join(sorted(allowed_set))

    def _write_file(path: str, content: str) -> str:
        ext = Path(path).suffix.lower()
        if ext not in allowed_set:
            return (
                f"Permission denied: this agent may only write {ext_label} files, "
                f"but '{path}' has extension '{ext}'."
            )
        try:
            resolved = _resolve_safe(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"Written {len(content)} characters to '{path}'."
        except PermissionError as exc:
            return f"ERROR: {exc}"
        except Exception as exc:
            return f"ERROR writing '{path}': {exc}"

    return StructuredTool.from_function(
        func=_write_file,
        name="write_file",
        description=(
            f"Write text content to a file inside the dbt project. "
            f"Only {ext_label} files are permitted for this agent. "
            "Path must be relative to the dbt project directory."
        ),
    )
