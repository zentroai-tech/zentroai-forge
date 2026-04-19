from __future__ import annotations

from forge_integrations.recipes.pg_readonly_query import tool


def test_pg_contract_success(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost/db")

    def fake_allowlist():
        return {
            "q1": {
                "sql": "SELECT id FROM patients WHERE id = %(patient_id)s",
                "params": ["patient_id"],
            }
        }

    def fake_execute(sql, params, max_rows):
        assert "SELECT" in sql
        assert params["patient_id"] == "p1"
        return [{"id": "p1"}]

    monkeypatch.setattr(tool, "_load_allowlist", fake_allowlist)
    monkeypatch.setattr(tool, "_execute", fake_execute)
    out = tool.run({"query_id": "q1", "params": {"patient_id": "p1"}})
    assert out["ok"] is True
    assert out["row_count"] == 1

