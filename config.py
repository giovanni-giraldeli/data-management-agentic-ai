"""Central configuration for the Agentic AI Data Management system."""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# LLM – provider-agnostic via LangChain's init_chat_model.
# Set LLM_MODEL to any model supported by your installed provider package, e.g.:
#   openai/gpt-4o          (requires langchain-openai + OPENAI_API_KEY)
#   anthropic/claude-3-5-sonnet-20241022  (requires langchain-anthropic + ANTHROPIC_API_KEY)
#   google_genai/gemini-1.5-pro  (requires langchain-google-genai + GOOGLE_API_KEY)
# ---------------------------------------------------------------------------
LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-4o")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))

# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------
DUCKDB_PATH: str = os.getenv("DUCKDB_PATH", str(BASE_DIR / "data" / "warehouse.duckdb"))

# ---------------------------------------------------------------------------
# dbt
# ---------------------------------------------------------------------------
DBT_PROJECT_DIR: str = os.getenv("DBT_PROJECT_DIR", str(BASE_DIR / "agentic_dbt_project"))
DBT_PROFILES_DIR: str = os.getenv("DBT_PROFILES_DIR", str(BASE_DIR / "profiles"))

# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------
AUDIT_LOG_PATH: str = os.getenv("AUDIT_LOG_PATH", str(BASE_DIR / "audit_trail.json"))

# ---------------------------------------------------------------------------
# MCP server entry points (absolute paths so subprocesses can find them)
# ---------------------------------------------------------------------------
PYTHON_EXECUTABLE: str = sys.executable
MCP_DUCKDB_SERVER: str = str(BASE_DIR / "mcp_servers" / "duckdb_server.py")

# Official dbt-mcp entry point installed in the project venv (requires Python >=3.12).
# dbt-core and dbt-duckdb live in the same venv so CLI commands work correctly.
_venv_scripts = BASE_DIR / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
MCP_DBT_SERVER: str = str(_venv_scripts / ("dbt-mcp.exe" if sys.platform == "win32" else "dbt-mcp"))
