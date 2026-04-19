# Backend

FastAPI backend for Zentro Forge.

## Stack

- Python `3.11`
- FastAPI
- Pydantic v2
- SQLModel + SQLite
- Optional LangChain and LlamaIndex adapters

## Run locally

```bash
cd backend
pip install -e ".[dev]"
py -3.11 -m uvicorn agent_compiler.main:app --reload --port 8000
```

Open:

- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Important environment variables

| Variable | Purpose |
|---|---|
| `AGENT_COMPILER_DATABASE_URL` | Database connection string |
| `AGENT_COMPILER_API_KEY` | Optional API key protection |
| `AGENT_COMPILER_REQUIRE_AUTH_FOR_READS` | Protect read endpoints too |
| `AGENT_COMPILER_CORS_ALLOW_ORIGINS` | Allowed frontend origins |
| `AGENT_COMPILER_EXPORT_TEMP_DIR` | Export workspace location |
| `FORGE_MASTER_KEY` | Credential encryption key |
| `AGENT_COMPILER_MCP_ENABLED` | Enable MCP execution |
| `AGENT_COMPILER_MCP_ALLOWED_COMMANDS` | MCP executable allowlist |
| `AGENT_COMPILER_MCP_ALLOWED_TOOLS` | MCP tool allowlist |

## IR contract

Only `ir_version: "2"` is supported.

Core models:

- `src/agent_compiler/models/ir.py`: shared graph, node, edge, and parsing helpers
- `src/agent_compiler/models/ir_v2.py`: canonical multi-agent IR schema

## Main areas

- `routers/`: HTTP endpoints
- `services/`: export, run, eval, replay, GitOps, credentials
- `runtime/`: execution logic
- `tools/`: tool contracts and registry
- `templates/`: starter IR templates
- `observability/`: logging and tracing

## Test commands

```bash
cd backend
py -3.11 -m ruff check src tests
py -3.11 -m pytest tests -q
```

For broader context, see the [root README](../README.md) and [API docs](../docs/API.md).
