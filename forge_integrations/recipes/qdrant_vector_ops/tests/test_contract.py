"""Contract tests for qdrant_vector_ops.

All tests use monkeypatching — no real Qdrant instance is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from forge_integrations.recipes.qdrant_vector_ops import tool


def _mock_client():
    client = MagicMock()
    # get_collections returns an object with .collections list
    collection_info = SimpleNamespace(name="test-col")
    client.get_collections.return_value = SimpleNamespace(collections=[collection_info])
    # search returns list of scored points
    hit = SimpleNamespace(id="vec-1", score=0.95, payload={"text": "hello"})
    client.search.return_value = [hit]
    return client


# ---------------------------------------------------------------------------
# ensure_collection
# ---------------------------------------------------------------------------


def test_ensure_collection_creates_new(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    def fake_ensure(args):
        return {"ok": True, "collection": args["collection"], "created": True}

    monkeypatch.setattr(tool, "_ensure_collection", fake_ensure)
    out = tool.run({"operation": "ensure_collection", "collection": "docs", "size": 768})
    assert out["ok"] is True
    assert out["created"] is True


def test_ensure_collection_skips_existing(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    def fake_ensure(args):
        return {"ok": True, "collection": args["collection"], "created": False}

    monkeypatch.setattr(tool, "_ensure_collection", fake_ensure)
    out = tool.run({"operation": "ensure_collection", "collection": "docs", "size": 768})
    assert out["created"] is False


def test_ensure_collection_schema_rejects_missing_size(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    # Bypass the qdrant-client model imports by patching _ensure_collection back to original
    # and testing schema validation only (no real client call)
    with pytest.raises((ValueError, RuntimeError)):
        # missing 'size' — schema should reject
        tool.run({"operation": "ensure_collection", "collection": "docs"})


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def test_upsert_success(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    def fake_upsert(args):
        return {"ok": True, "collection": args["collection"], "upserted": len(args["points"])}

    monkeypatch.setattr(tool, "_upsert", fake_upsert)
    out = tool.run({
        "operation": "upsert",
        "collection": "docs",
        "points": [
            {"id": "v1", "vector": [0.1, 0.2, 0.3], "payload": {"text": "alpha"}},
            {"id": "v2", "vector": [0.4, 0.5, 0.6]},
        ],
    })
    assert out["ok"] is True
    assert out["upserted"] == 2


def test_upsert_schema_rejects_empty_points(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "upsert", "collection": "docs", "points": []})


def test_upsert_schema_rejects_point_without_vector(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({
            "operation": "upsert",
            "collection": "docs",
            "points": [{"id": "v1"}],  # missing vector
        })


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


def test_query_success(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    def fake_query(args):
        return {"matches": [{"id": "v1", "score": 0.95, "payload": {"text": "hello"}}]}

    monkeypatch.setattr(tool, "_query", fake_query)
    out = tool.run({
        "operation": "query",
        "collection": "docs",
        "vector": [0.1, 0.2, 0.3],
        "top_k": 5,
    })
    assert len(out["matches"]) == 1
    assert out["matches"][0]["id"] == "v1"
    assert out["matches"][0]["score"] == 0.95


def test_query_empty_results(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setattr(tool, "_query", lambda args: {"matches": []})
    out = tool.run({"operation": "query", "collection": "docs", "vector": [0.1, 0.2]})
    assert out["matches"] == []


def test_query_schema_rejects_missing_vector(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "query", "collection": "docs"})


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_success(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    def fake_delete(args):
        return {"ok": True, "collection": args["collection"], "deleted": len(args["ids"])}

    monkeypatch.setattr(tool, "_delete", fake_delete)
    out = tool.run({"operation": "delete", "collection": "docs", "ids": ["v1", "v2", "v3"]})
    assert out["ok"] is True
    assert out["deleted"] == 3


def test_delete_schema_rejects_empty_ids(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "delete", "collection": "docs", "ids": []})


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_unknown_operation_raises(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    with pytest.raises(RuntimeError, match="Unknown qdrant operation"):
        tool.run({"operation": "drop_everything"})


def test_missing_operation_raises(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    with pytest.raises(RuntimeError, match="Unknown qdrant operation"):
        tool.run({"collection": "docs"})
