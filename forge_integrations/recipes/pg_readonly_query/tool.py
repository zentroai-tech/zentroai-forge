"""Read-only Postgres query tool using allowlisted query IDs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from forge_integrations.shared.env import require_env
from forge_integrations.shared.schemas import load_schema, validate_payload

_DIR = Path(__file__).resolve().parent
_INPUT_SCHEMA = load_schema(_DIR / "schemas" / "pg_readonly_query.input.json")
_OUTPUT_SCHEMA = load_schema(_DIR / "schemas" / "pg_readonly_query.output.json")


def _allowlist_path() -> Path:
    raw = os.environ.get("PG_QUERY_ALLOWLIST_PATH", "").strip()
    if raw:
        return Path(raw)
    return _DIR / "queries" / "query_allowlist.json"


def _load_allowlist() -> dict[str, dict[str, Any]]:
    payload = json.loads(_allowlist_path().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("PG query allowlist must be a JSON object.")
    return payload


def _validate_readonly_sql(sql: str) -> None:
    normalized = sql.strip().lower()
    if not normalized.startswith("select "):
        raise RuntimeError("Only SELECT statements are allowed.")
    blocked = (" insert ", " update ", " delete ", " drop ", " alter ", " create ", " grant ", " revoke ")
    wrapped = f" {normalized} "
    if any(keyword in wrapped for keyword in blocked):
        raise RuntimeError("Mutating SQL is not allowed.")


def _execute(sql: str, params: dict[str, Any], max_rows: int) -> list[dict[str, Any]]:
    database_url = require_env("DATABASE_URL")
    connect_timeout_s = int(os.environ.get("PG_CONNECT_TIMEOUT_S", "5") or "5")
    statement_timeout_ms = int(os.environ.get("PG_STATEMENT_TIMEOUT_MS", "5000") or "5000")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("psycopg is required for pg_readonly_query") from exc

    with psycopg.connect(database_url, connect_timeout=connect_timeout_s, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
            cur.execute(sql, params)
            rows = cur.fetchmany(max_rows)
    return [dict(row) for row in rows]


def run(args: dict[str, Any]) -> dict[str, Any]:
    """Execute readonly allowlisted query by query_id."""
    validate_payload(schema=_INPUT_SCHEMA, payload=args, context="pg_readonly_query input")

    allowlist = _load_allowlist()
    query_id = str(args["query_id"])
    if query_id not in allowlist:
        raise RuntimeError(f"Query ID not allowlisted: {query_id}")

    spec = allowlist[query_id] or {}
    sql = str(spec.get("sql") or "").strip()
    if not sql:
        raise RuntimeError(f"Allowlist entry missing SQL: {query_id}")
    _validate_readonly_sql(sql)

    required_params = [str(p) for p in (spec.get("params") or [])]
    params = args.get("params") or {}
    if not isinstance(params, dict):
        raise RuntimeError("params must be an object")
    missing = [name for name in required_params if name not in params]
    if missing:
        raise RuntimeError(f"Missing required params for query_id={query_id}: {missing}")

    max_rows = int(args.get("max_rows", 100) or 100)
    rows = _execute(sql, params, max_rows=max_rows)
    output: dict[str, Any] = {
        "ok": True,
        "query_id": query_id,
        "row_count": len(rows),
        "rows": rows,
    }
    validate_payload(schema=_OUTPUT_SCHEMA, payload=output, context="pg_readonly_query output")
    return output

