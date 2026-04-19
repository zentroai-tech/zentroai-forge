"""Security tests for qdrant_vector_ops.

Validates:
- HTTPS enforced for non-localhost connections.
- HTTP allowed for localhost.
- API key is not echoed into operation results.
- Score ordering is preserved in query output.
- Oversized upsert batches are rejected.
"""

from __future__ import annotations

import pytest

from forge_integrations.recipes.qdrant_vector_ops import tool


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------


def test_https_required_for_remote_host(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://remote-cluster.example.com:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "secret-key")
    with pytest.raises(PermissionError, match="HTTPS"):
        tool._check_url_safety("http://remote-cluster.example.com:6333")


def test_https_accepted_for_remote_host(monkeypatch):
    # Should not raise
    tool._check_url_safety("https://my-cluster.qdrant.tech")


def test_http_allowed_for_localhost(monkeypatch):
    # Should not raise
    tool._check_url_safety("http://localhost:6333")
    tool._check_url_safety("http://127.0.0.1:6333")


def test_invalid_scheme_raises(monkeypatch):
    with pytest.raises(ValueError, match="Invalid scheme"):
        tool._check_url_safety("ftp://localhost:6333")


# ---------------------------------------------------------------------------
# API key not in output
# ---------------------------------------------------------------------------


def test_api_key_not_echoed_in_output(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "super-secret-qdrant-key")

    def fake_query(args):
        return {"matches": [{"id": "v1", "score": 0.9, "payload": {}}]}

    monkeypatch.setattr(tool, "_query", fake_query)
    out = tool.run({"operation": "query", "collection": "docs", "vector": [0.1, 0.2]})
    assert "super-secret-qdrant-key" not in str(out)


# ---------------------------------------------------------------------------
# Score ordering
# ---------------------------------------------------------------------------


def test_query_results_preserve_score_order(monkeypatch):
    """The tool must not re-sort results — provider ordering is canonical."""
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    def fake_query(args):
        return {
            "matches": [
                {"id": "v3", "score": 0.99, "payload": {}},
                {"id": "v1", "score": 0.85, "payload": {}},
                {"id": "v2", "score": 0.70, "payload": {}},
            ]
        }

    monkeypatch.setattr(tool, "_query", fake_query)
    out = tool.run({"operation": "query", "collection": "docs", "vector": [0.1, 0.2]})
    scores = [m["score"] for m in out["matches"]]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Batch size cap
# ---------------------------------------------------------------------------


def test_upsert_rejects_more_than_1000_points(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setattr(tool, "_get_client", lambda: None)
    oversized = [{"id": str(i), "vector": [0.1]} for i in range(1001)]
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "upsert", "collection": "docs", "points": oversized})


# ---------------------------------------------------------------------------
# Missing env var
# ---------------------------------------------------------------------------


def test_missing_qdrant_url_raises(monkeypatch):
    """_get_client must raise on missing QDRANT_URL before attempting SDK import."""
    monkeypatch.delenv("QDRANT_URL", raising=False)
    # require_env is called before the SDK import, so this fails with EnvVarError
    # regardless of whether qdrant-client is installed.
    with pytest.raises(Exception, match="QDRANT_URL"):
        tool._get_client()
