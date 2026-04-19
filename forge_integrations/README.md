# Forge Integrations Library

This folder is a reference library of copy/paste integrations for Forge exports.

Scope:
- It is part of the Forge repo only.
- It is **not** auto-included in exported projects.
- Use it as a scaffold for production integrations.

Recipe dependencies (copy as needed into your exported repo):
- `requests`
- `jsonschema`
- `fastapi` (only for inbound gateway example)
- `psycopg` (only for Postgres recipe)
- `qdrant-client` (only for Qdrant recipe)
- `pinecone-client` (only for Pinecone recipe)

## Included recipes

1. `telegram_send_message` (outbound)
2. `whatsapp_send_message` (outbound) + optional inbound FastAPI gateway example
3. `pg_readonly_query` (read-only Postgres via allowlisted query IDs)
4. `rag_retriever_citations` (RAG retrieval with deterministic C1..Cn citation IDs)
5. `qdrant_vector_ops` (Qdrant: ensure_collection / upsert / query / delete)
6. `pinecone_vector_ops` (Pinecone: ensure_index / upsert / query / delete)

## How to use in an exported repo

1. Copy tool implementation into exported repo:
   - `tools/<tool_name>.py`
2. Copy schemas into exported repo:
   - `runtime/schemas/tools/<tool_name>.input.json`
   - `runtime/schemas/tools/<tool_name>.output.json`
3. Register the tool in:
   - `runtime/tools/registry.py` (or your tool registry file)
4. Allowlist the tool in:
   - `settings.py` under `FLOW_POLICIES["tool_allowlist"]`
5. Add env vars to:
   - `.env.example`
   - `runtime/config.py` if you keep typed config there
6. Copy tests and run:
   - `pytest -q tests`

## Shared helpers

`forge_integrations/shared/` provides small helpers you can copy:
- `env.py`: required env var reader with safe errors
- `http.py`: HTTP JSON wrapper with timeout + retries
- `schemas.py`: JSON schema load + validate
- `citations_renderer.py`: format bibliography strings and normalise `[Cn]` markers
- `citation_required_check.py`: enforce citation presence in RAG-generated paragraphs
- `vector_router.py`: provider-agnostic router for vector DB ops (qdrant/pinecone)
- `schemas/`: provider-agnostic JSON schemas for vector operations

## Recipe folders

- `forge_integrations/recipes/telegram_send_message/`
- `forge_integrations/recipes/whatsapp_cloud/`
- `forge_integrations/recipes/pg_readonly_query/`
- `forge_integrations/recipes/rag_retriever_citations/`
- `forge_integrations/recipes/qdrant_vector_ops/`
- `forge_integrations/recipes/pinecone_vector_ops/`

Each recipe includes:
- input/output schemas
- tool implementation
- env vars
- minimal tests (contract + failure/security)

## Test and eval commands (in exported repo)

```bash
pytest -q tests
python -m evals.run --suite smoke
python -m evals.run --suite regression
curl -s http://127.0.0.1:9090/healthz
curl -s http://127.0.0.1:9090/metrics
```
