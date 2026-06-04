# Agentic AI Data Management

LangGraph-based multi-agent system for automating Data Management processes on top of a dbt + DuckDB stack. Built as part of a Master's thesis at NOVA IMS.

---

## Architecture

```
User input
    │
    ▼
┌─────────┐     routes     ┌────────────────────┐
│ Planner │ ──────────────►│ data_profile_worker │
│ (super- │◄───────────────│ metadata_worker     │
│  visor) │    result      │ data_modeling_worker│
└─────────┘                │ data_quality_worker │
                           │ semantical_worker   │
                           └────────────────────┘
              ↕ stdio MCP                ↕ stdio MCP
         ┌─────────┐               ┌──────────┐
         │ DuckDB  │               │   dbt    │
         │  MCP    │               │   MCP    │
         │ Server  │               │  Server  │
         └─────────┘               └──────────┘
```

The **Planner** is the supervisor: it creates a plan, routes tasks to workers, reviews results, and decides when the workflow is complete.

Each agent has strictly scoped tool access (principle of least privilege, thesis §4.4.3):

| Agent | DuckDB | dbt commands | File writes |
|---|---|---|---|
| Planner | list_tables, describe_table | — | none |
| Data Profile Worker | list, describe, query, sample | — | `.md` |
| Metadata Worker | — | docs generate, ls | `.yml` |
| Data Modeling Worker | list, describe, query | run, ls | `.sql` |
| Data Quality Worker | — | test, ls | `.yml` |
| Semantical Worker | list, describe, query | run, docs generate, ls | `.yml .md .sql` |

---

## Quick start

### 1. Install dependencies

Python **3.12 or 3.13** is required (`dbt-mcp` constraint). If you use [`uv`](https://docs.astral.sh/uv/) (recommended), it reads `.python-version` automatically:

```bash
# Create a Python 3.13 venv and install everything in one step
uv venv --python 3.13 .venv
uv pip install -r requirements.txt

# Activate the venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install exactly ONE LLM provider package, e.g.:
uv pip install langchain-openai      # for OpenAI / Azure
# uv pip install langchain-anthropic # for Anthropic Claude
# uv pip install langchain-google-genai  # for Google Gemini
# uv pip install langchain-ollama    # for local Ollama models
```

> **Without uv:** `python3.13 -m venv .venv && pip install -r requirements.txt` works the same way.

### 2. Configure the LLM provider

Copy the environment template and fill in the values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Choose the model (provider/model-name format used by LangChain init_chat_model)
LLM_MODEL=openai/gpt-4o

# Provide the API key for your chosen provider
OPENAI_API_KEY=sk-...
```

Supported `LLM_MODEL` values (examples):

| Provider | LLM_MODEL | Package |
|---|---|---|
| OpenAI | `openai/gpt-4o` | `langchain-openai` |
| Anthropic | `anthropic/claude-3-5-sonnet-20241022` | `langchain-anthropic` |
| Google GenAI | `google_genai/gemini-1.5-pro` | `langchain-google-genai` |
| Ollama (local) | `ollama/llama3.1` | `langchain-ollama` |

The system uses `langchain.chat_models.init_chat_model(LLM_MODEL)` — any provider whose LangChain integration package is installed will work without any code changes.

### 3. Load source data into DuckDB

Place the source CSV/Parquet files in `data/` and load them into the warehouse. Example for CSV files:

```python
import duckdb
conn = duckdb.connect("data/warehouse.duckdb")
conn.execute("CREATE TABLE aspnet_membership AS SELECT * FROM read_csv_auto('data/aspnet_membership.csv')")
conn.execute("CREATE TABLE aspnet_profile   AS SELECT * FROM read_csv_auto('data/aspnet_profile.csv')")
conn.execute("CREATE TABLE domain           AS SELECT * FROM read_csv_auto('data/domain.csv')")
conn.execute("CREATE TABLE domain_group     AS SELECT * FROM read_csv_auto('data/domain_group.csv')")
conn.close()
```

### 4. Run the pipeline

```bash
python main.py
```

Or pass a custom task:

```bash
python main.py "Profile the source tables and build a dim_customers model only."
```

The pipeline will:
1. Start the DuckDB and dbt MCP servers as background processes
2. Route through the Planner → Workers according to the task
3. Write dbt model files, YAML documentation, Markdown reports, and semantic layer definitions
4. Log every agent interaction to `audit_trail.json`

---

## Audit trail

All agent interactions are appended to `audit_trail.json` (path configurable via `AUDIT_LOG_PATH`). Each entry has the following structure:

```json
{
  "timestamp": "2026-01-01T12:00:00.000000+00:00",
  "agent_id": "data_modeling_worker",
  "event_type": "tool_start",
  "tool_name": "dbt_run",
  "tool_input": "{\"model_selector\": \"dim_customers\"}"
}
```

`event_type` values: `llm_start`, `llm_end`, `tool_start`, `tool_end`, `chain_start`, `chain_end`, `llm_error`, `tool_error`.

---

## Project structure

```
├── agents/                  # Agent system prompts & permission declarations
│   ├── planner.py
│   ├── data_profile_worker.py
│   ├── metadata_worker.py
│   ├── data_modeling_worker.py
│   ├── data_quality_worker.py
│   └── semantical_worker.py
├── audit/
│   └── callbacks.py         # LangGraph BaseCallbackHandler → audit_trail.json
├── mcp_servers/
│   ├── duckdb_server.py     # DuckDB MCP server (FastMCP, SELECT-only)
│   └── dbt_server.py        # dbt MCP server (FastMCP, scoped CLI commands)
├── orchestrator/
│   └── graph.py             # LangGraph StateGraph, supervisor routing logic
├── tools/
│   └── filesystem.py        # File-system tools with extension-scoped write access
├── agentic_dbt_project/     # dbt project (models, sources, tests, docs)
├── profiles/
│   └── profiles.yml         # dbt DuckDB connection profile
├── data/                    # DuckDB warehouse file (gitignored)
├── config.py                # Central configuration (reads .env)
├── main.py                  # Entry point
├── mcp_config.json          # MCP server config reference (documentation)
├── .env.example             # Environment variable template
└── requirements.txt
```

---

## Design notes / open questions

The following items in the thesis were interpreted with reasonable assumptions. They are flagged here for review:

1. **"GitHub" access** — The thesis refers to "GitHub read/write access" for agents. In this implementation that is interpreted as local file-system access to the dbt project directory, since all development occurs in a git worktree. A production deployment could substitute the filesystem tools with GitHub API tools (e.g. via PyGithub or the GitHub MCP server).

2. **Branch-per-agent isolation** — The thesis states agents should commit to separate branches. This implementation writes files directly to the working tree and relies on the existing git worktree isolation. Adding git commit / push tools per agent would require extending the filesystem tools with `git` commands, which is outside the tool permissions explicitly listed in §4.4.3.

3. **A2A protocol** — The thesis mentions A2A (Agent-to-Agent) as a future communication layer. LangGraph's state-passing graph fulfils the inter-agent communication requirement without a separate A2A server. An A2A layer could be added if agents need to be deployed as independent services.

4. **dbt Semantic Models vs. legacy metrics** — The Semantical Worker targets dbt's MetricFlow / Semantic Models syntax. If the installed `dbt-core` version does not support MetricFlow, the worker will fall back to the legacy `metrics:` YAML block. The agent's system prompt covers both cases.
