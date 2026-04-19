# pg_readonly_query

Read-only Postgres query recipe with allowlisted query IDs.

Important:
- The model must not send raw SQL.
- Input provides `query_id` + `params`.
- SQL is resolved from local allowlist file only.

## Env vars

- `DATABASE_URL` (required)
- `PG_CONNECT_TIMEOUT_S` (optional, default `5`)
- `PG_STATEMENT_TIMEOUT_MS` (optional, default `5000`)
- `PG_QUERY_ALLOWLIST_PATH` (optional, default `queries/query_allowlist.json`)

## Copy into exported repo

- Tool: `tools/pg_readonly_query.py`
- Schemas:
  - `runtime/schemas/tools/pg_readonly_query.input.json`
  - `runtime/schemas/tools/pg_readonly_query.output.json`
- Query allowlist file:
  - `tools/queries/query_allowlist.json`
- Register in: `runtime/tools/registry.py`
- Allowlist in: `settings.py` (`FLOW_POLICIES["tool_allowlist"]`)
