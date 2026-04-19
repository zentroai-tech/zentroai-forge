from __future__ import annotations

import pytest

from forge_integrations.recipes.pg_readonly_query import tool


def test_pg_unknown_query_id(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost/db")
    monkeypatch.setattr(tool, "_load_allowlist", lambda: {})
    with pytest.raises(RuntimeError):
        tool.run({"query_id": "unknown"})


def test_pg_rejects_mutating_sql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost/db")
    monkeypatch.setattr(
        tool,
        "_load_allowlist",
        lambda: {"bad": {"sql": "UPDATE patients SET name='x' WHERE id=%(id)s", "params": ["id"]}},
    )
    with pytest.raises(RuntimeError):
        tool.run({"query_id": "bad", "params": {"id": "1"}})

