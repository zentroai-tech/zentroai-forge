"""Security tests for pinecone_vector_ops.

Validates:
- API key is not echoed into operation outputs.
- Score ordering is preserved (Pinecone returns results sorted by score).
- Oversized upsert batches are rejected by schema.
- Missing required env vars raise immediately.
- vector_router routes correctly to pinecone backend.
"""

from __future__ import annotations

import pytest

from forge_integrations.recipes.pinecone_vector_ops import tool
from forge_integrations.shared import vector_router


# ---------------------------------------------------------------------------
# API key not in output
# ---------------------------------------------------------------------------


def test_api_key_not_echoed_in_output(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "super-secret-pinecone-key")

    def fake_query(args):
        return {"matches": [{"id": "v1", "score": 0.9, "payload": {}}]}

    monkeypatch.setattr(tool, "_query", fake_query)
    out = tool.run({"operation": "query", "collection": "my-index", "vector": [0.1]})
    assert "super-secret-pinecone-key" not in str(out)


# ---------------------------------------------------------------------------
# Score ordering
# ---------------------------------------------------------------------------


def test_query_results_preserve_score_order(monkeypatch):
    """Tool must return results in the order provided by the provider."""
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")

    def fake_query(args):
        return {
            "matches": [
                {"id": "v3", "score": 0.99, "payload": {}},
                {"id": "v1", "score": 0.85, "payload": {}},
                {"id": "v2", "score": 0.72, "payload": {}},
            ]
        }

    monkeypatch.setattr(tool, "_query", fake_query)
    out = tool.run({"operation": "query", "collection": "idx", "vector": [0.1]})
    scores = [m["score"] for m in out["matches"]]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Batch size cap
# ---------------------------------------------------------------------------


def test_upsert_rejects_more_than_1000_points(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(tool, "_get_client", lambda: None)
    oversized = [{"id": str(i), "vector": [0.1]} for i in range(1001)]
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "upsert", "collection": "idx", "points": oversized})


# ---------------------------------------------------------------------------
# Missing env var
# ---------------------------------------------------------------------------


def test_missing_api_key_raises(monkeypatch):
    """_get_client must raise on missing PINECONE_API_KEY before SDK import."""
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    # require_env is called before the SDK import, so EnvVarError is raised
    # regardless of whether pinecone-client is installed.
    with pytest.raises(Exception, match="PINECONE_API_KEY"):
        tool._get_client()


# ---------------------------------------------------------------------------
# vector_router integration
# ---------------------------------------------------------------------------


def test_vector_router_routes_to_pinecone(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")

    def fake_query(args):
        return {"matches": [{"id": "p1", "score": 0.77, "payload": {}}]}

    monkeypatch.setattr(tool, "_query", fake_query)

    out = vector_router.vector_query({
        "provider": "pinecone",
        "collection": "my-index",
        "vector": [0.1, 0.2],
    })
    assert out["matches"][0]["id"] == "p1"


def test_vector_router_unknown_provider_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="Unknown vector provider"):
        vector_router.vector_query({
            "provider": "weaviate",
            "collection": "idx",
            "vector": [0.1],
        })


def test_vector_router_missing_provider_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="Missing 'provider'"):
        vector_router.vector_upsert({
            "collection": "idx",
            "points": [{"id": "v1", "vector": [0.1]}],
        })
