#!/usr/bin/env python3
"""dbt MCP Server.

Exposes dbt CLI commands as tools so agents can materialise models,
run tests, generate docs, and list resources — without direct access
to the underlying data warehouse connection.

Tools
-----
dbt_run              Materialise one or all dbt models.
dbt_test             Execute dbt data-quality tests.
dbt_docs_generate    Generate the static dbt documentation site.
dbt_ls               List dbt resources in the project.

Usage
-----
Launched automatically by the orchestrator via stdio transport.
Environment variables:
  DBT_PROJECT_DIR   Path to the dbt project directory (default: agentic_dbt_project).
  DBT_PROFILES_DIR  Path to the profiles directory   (default: profiles).
"""

import os
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", str(_REPO_ROOT / "agentic_dbt_project"))
DBT_PROFILES_DIR = os.environ.get("DBT_PROFILES_DIR", str(_REPO_ROOT / "profiles"))

mcp = FastMCP("dbt Server")


def _run_dbt(args: list[str]) -> str:
    """Execute a dbt command and return combined stdout + stderr."""
    cmd = [
        sys.executable, "-m", "dbt",
        *args,
        "--project-dir", DBT_PROJECT_DIR,
        "--profiles-dir", DBT_PROFILES_DIR,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() if output.strip() else "(no output)"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def dbt_run(model_selector: str = "") -> str:
    """Materialise dbt models by executing their SQL transformations.

    Parameters
    ----------
    model_selector:
        Optional dbt node selector (e.g. ``dim_customers`` or ``+fct_usage``).
        Leave empty to run all models.
    """
    args = ["run"]
    if model_selector:
        args += ["--select", model_selector]
    return _run_dbt(args)


@mcp.tool()
def dbt_test(model_selector: str = "") -> str:
    """Run dbt data-quality tests and return the test report.

    Parameters
    ----------
    model_selector:
        Optional selector to run tests for a subset of models.
        Leave empty to run all tests.
    """
    args = ["test"]
    if model_selector:
        args += ["--select", model_selector]
    return _run_dbt(args)


@mcp.tool()
def dbt_docs_generate() -> str:
    """Generate the dbt documentation artefacts (catalog.json, manifest.json)."""
    return _run_dbt(["docs", "generate"])


@mcp.tool()
def dbt_ls(resource_type: str = "", model_selector: str = "") -> str:
    """List dbt resources registered in the project.

    Parameters
    ----------
    resource_type:
        Filter by resource type, e.g. ``model``, ``test``, ``source``, ``metric``.
        Leave empty to list everything.
    model_selector:
        Optional node selector to narrow the listing.
    """
    args = ["ls"]
    if resource_type:
        args += ["--resource-type", resource_type]
    if model_selector:
        args += ["--select", model_selector]
    return _run_dbt(args)


if __name__ == "__main__":
    mcp.run(transport="stdio")
