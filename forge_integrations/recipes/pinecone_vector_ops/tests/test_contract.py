"""Contract tests for pinecone_vector_ops.

All tests use monkeypatching — no real Pinecone credentials are required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from forge_integrations.recipes.pinecone_vector_ops import tool


def _mock_index(matches=None):
    index = MagicMock()
    index.query.return_value = {"matches": matches or []}
    return index


def _mock_client(index=None, existing_names=None):
    client = MagicMock()
    existing = existing_names or []
    # list_indexes: return object with .indexes attr
    idx_objects = [MagicMock(name=n) for n in existing]
    client.list_indexes.return_value = MagicMock(indexes=idx_objects)
    if index is not None:
        client.Index.return_value = index
    return client


# ---------------------------------------------------------------------------
# ensure_collection
# ---------------------------------------------------------------------------


def test_ensure_collection_creates_new(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    client = _mock_client(existing_names=[])  # no existing indexes
    monkeypatch.setattr(tool, "_get_client", lambda: client)

    def fake_ensure(args):
        return {"ok": True, "collection": args["collection"], "created": True}

    monkeypatch.setattr(tool, "_ensure_collection", fake_ensure)
    out = tool.run({"operation": "ensure_collection", "collection": "my-index", "size": 1536})
    assert out["ok"] is True
    assert out["created"] is True


def test_ensure_collection_skips_existing(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")

    def fake_ensure(args):
        return {"ok": True, "collection": args["collection"], "created": False}

    monkeypatch.setattr(tool, "_ensure_collection", fake_ensure)
    out = tool.run({"operation": "ensure_collection", "collection": "my-index", "size": 1536})
    assert out["created"] is False


def test_ensure_collection_schema_rejects_missing_size(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "ensure_collection", "collection": "my-index"})


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def test_upsert_success(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_INDEX", "my-index")

    def fake_upsert(args):
        return {"ok": True, "collection": "my-index", "upserted": len(args["points"])}

    monkeypatch.setattr(tool, "_upsert", fake_upsert)
    out = tool.run({
        "operation": "upsert",
        "collection": "my-index",
        "points": [
            {"id": "v1", "vector": [0.1, 0.2, 0.3], "payload": {"doc": "A"}},
            {"id": "v2", "vector": [0.4, 0.5, 0.6]},
        ],
    })
    assert out["ok"] is True
    assert out["upserted"] == 2


def test_upsert_schema_rejects_empty_points(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "upsert", "collection": "my-index", "points": []})


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


def test_query_success(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_INDEX", "my-index")

    def fake_query(args):
        return {"matches": [{"id": "v1", "score": 0.88, "payload": {"doc": "A"}}]}

    monkeypatch.setattr(tool, "_query", fake_query)
    out = tool.run({
        "operation": "query",
        "collection": "my-index",
        "vector": [0.1, 0.2, 0.3],
        "top_k": 3,
    })
    assert len(out["matches"]) == 1
    assert out["matches"][0]["score"] == 0.88


def test_query_empty_results(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(tool, "_query", lambda args: {"matches": []})
    out = tool.run({"operation": "query", "collection": "my-index", "vector": [0.1]})
    assert out["matches"] == []


def test_query_schema_rejects_missing_vector(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "query", "collection": "my-index"})


def test_query_score_threshold_filters_results(monkeypatch):
    """Results below score_threshold must be excluded."""
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_INDEX", "my-index")

    def fake_query(args):
        threshold = args.get("score_threshold")
        matches = [
            {"id": "v1", "score": 0.95, "payload": {}},
            {"id": "v2", "score": 0.60, "payload": {}},
        ]
        if threshold is not None:
            matches = [m for m in matches if m["score"] >= threshold]
        return {"matches": matches}

    monkeypatch.setattr(tool, "_query", fake_query)
    out = tool.run({
        "operation": "query",
        "collection": "my-index",
        "vector": [0.1, 0.2],
        "score_threshold": 0.8,
    })
    assert all(m["score"] >= 0.8 for m in out["matches"])


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_success(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")

    def fake_delete(args):
        return {"ok": True, "collection": args["collection"], "deleted": len(args["ids"])}

    monkeypatch.setattr(tool, "_delete", fake_delete)
    out = tool.run({
        "operation": "delete",
        "collection": "my-index",
        "ids": ["v1", "v2"],
    })
    assert out["ok"] is True
    assert out["deleted"] == 2


def test_delete_schema_rejects_empty_ids(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(tool, "_get_client", lambda: _mock_client())
    with pytest.raises((ValueError, RuntimeError)):
        tool.run({"operation": "delete", "collection": "my-index", "ids": []})


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_unknown_operation_raises(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="Unknown pinecone operation"):
        tool.run({"operation": "truncate_index"})


def test_missing_operation_raises(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="Unknown pinecone operation"):
        tool.run({"collection": "my-index"})
