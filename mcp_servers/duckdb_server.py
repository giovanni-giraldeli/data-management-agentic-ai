#!/usr/bin/env python3
"""DuckDB MCP Server.

Exposes four read-only tools so agents can inspect and query the data
warehouse without the ability to modify any data.

Tools
-----
duckdb_list_tables      List all tables in the warehouse (metadata only).
duckdb_describe_table   Describe the schema of a single table.
duckdb_query            Execute a SELECT statement (write statements are blocked).
duckdb_get_table_sample Return a small sample of rows from a table.

Usage
-----
Launched automatically by the orchestrator via stdio transport.
Set DUCKDB_PATH env var to point at your .duckdb file (default: data/warehouse.duckdb
relative to the repo root).
"""

import os
import sys
from pathlib import Path
from typing import Any

import duckdb
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Bootstrap – make the repo root importable when run as a subprocess
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", str(_REPO_ROOT / "data" / "warehouse.duckdb"))

mcp = FastMCP("DuckDB Server")


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DUCKDB_PATH, read_only=True)


def _format_table(rows: list[tuple[Any, ...]], columns: list[str]) -> str:
    """Render *rows* and *columns* as a plain-text aligned table.

    Avoids pandas / numpy so the server has no heavy optional dependencies.
    """
    if not rows:
        return "(no rows)"
    col_widths = [len(c) for c in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val) if val is not None else ""))
    def _fmt_row(vals: tuple[Any, ...]) -> str:
        return "  ".join(
            (str(v) if v is not None else "").ljust(col_widths[i])
            for i, v in enumerate(vals)
        )
    header = "  ".join(c.ljust(col_widths[i]) for i, c in enumerate(columns))
    separator = "  ".join("-" * w for w in col_widths)
    lines = [header, separator] + [_fmt_row(r) for r in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def duckdb_list_tables() -> str:
    """List all tables and views available in the DuckDB data warehouse."""
    try:
        conn = _connect()
        rel = conn.execute("SHOW ALL TABLES")
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        conn.close()
        return _format_table(rows, cols)
    except Exception as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def duckdb_describe_table(table_name: str) -> str:
    """Describe the schema (column names, types, nullability) of a table.

    Parameters
    ----------
    table_name:
        Fully-qualified or unqualified table name, e.g. ``main.aspnet_membership``
        or simply ``aspnet_membership``.
    """
    try:
        conn = _connect()
        rel = conn.execute(f"DESCRIBE {table_name}")
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        conn.close()
        return _format_table(rows, cols)
    except Exception as exc:
        return f"ERROR: {exc}"


def _is_select(sql: str) -> bool:
    """Return True only if *sql* is a SELECT or WITH…SELECT statement.

    Strips leading whitespace and single-line SQL comments (``-- …``) before
    checking, so ``  -- comment\\nSELECT 1`` is accepted but
    ``  -- comment\\nDROP TABLE x`` is not.

    The primary enforcement layer is the ``read_only=True`` DuckDB connection;
    this check provides early, descriptive feedback to the agent.
    """
    import re
    # Remove leading SQL line comments and blank lines
    cleaned = re.sub(r"(--[^\n]*\n?|\s+)", " ", sql).strip().upper()
    return cleaned.startswith("SELECT") or cleaned.startswith("WITH")


@mcp.tool()
def duckdb_query(sql: str) -> str:
    """Execute a read-only SQL query and return the result as a table.

    Only SELECT (and WITH … SELECT) statements are permitted.  The connection
    is opened in ``read_only=True`` mode, so write operations are blocked at
    the database level regardless.  The result is truncated to 500 rows.

    Parameters
    ----------
    sql:
        A valid SELECT statement.
    """
    if not _is_select(sql):
        return "ERROR: Only SELECT (and WITH … SELECT) queries are permitted."
    try:
        conn = _connect()
        rel = conn.execute(sql)
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        conn.close()
        truncated = len(rows) > 500
        result = _format_table(rows[:500], cols)
        if truncated:
            result += f"\n\n[Truncated to 500 rows; total rows: {len(rows)}]"
        return result
    except Exception as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def duckdb_get_table_sample(table_name: str, limit: int = 10) -> str:
    """Return a small sample of rows from a table for profiling purposes.

    Parameters
    ----------
    table_name:
        Table to sample.
    limit:
        Number of rows to return (default 10, max 100).
    """
    limit = min(max(1, limit), 100)
    try:
        conn = _connect()
        rel = conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        conn.close()
        return _format_table(rows, cols)
    except Exception as exc:
        return f"ERROR: {exc}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
