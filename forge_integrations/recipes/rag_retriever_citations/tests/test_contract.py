"""Contract tests for rag_retriever_citations.

Validates:
- Schema enforcement (required fields, top_k bounds).
- Deterministic C1..Cn assignment by score desc / source_id / span.start.
- Multiple chunks from the same source share one citation_id.
- Empty results produce valid output.
"""

from __future__ import annotations

import pytest

from forge_integrations.recipes.rag_retriever_citations import tool


def _make_chunk(
    source_id: str,
    score: float,
    text: str = "chunk text",
    span_start: int = 0,
) -> dict:
    return {
        "text": text,
        "score": score,
        "source": {
            "source_id": source_id,
            "title": f"Title {source_id}",
            "url": f"https://example.com/{source_id}",
            "span": {"start": span_start, "end": span_start + len(text)},
        },
    }


def _fake_retrieve(chunks: list[dict]):
    return lambda q, top_k, filters: list(chunks)


def test_rag_contract_success(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    chunks = [
        _make_chunk("doc-a", 0.9),
        _make_chunk("doc-b", 0.8),
    ]
    monkeypatch.setattr(tool, "_retrieve", _fake_retrieve(chunks))

    out = tool.run({"query": "What is oncology?", "top_k": 2})

    assert out["query"] == "What is oncology?"
    assert out["total_chunks"] == 2
    assert len(out["chunks"]) == 2
    assert len(out["citations"]) == 2
    # Highest-scoring source gets C1
    assert out["citations"][0]["citation_id"] == "C1"
    assert out["citations"][0]["source_id"] == "doc-a"
    assert out["chunks"][0]["citation_id"] == "C1"


def test_citation_ids_deterministic_sort(monkeypatch):
    """C1 = highest score; tiebreak by source_id then span.start."""
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    chunks = [
        _make_chunk("doc-z", 0.7, span_start=0),
        _make_chunk("doc-a", 0.7, span_start=10),
        _make_chunk("doc-a", 0.9, span_start=0),  # highest score → C1
    ]
    monkeypatch.setattr(tool, "_retrieve", _fake_retrieve(chunks))

    out = tool.run({"query": "test"})

    cid_map = {c["source_id"]: c["citation_id"] for c in out["citations"]}
    assert cid_map["doc-a"] == "C1"
    assert cid_map["doc-z"] == "C2"


def test_tiebreak_source_id_order(monkeypatch):
    """When scores are equal, source_id alphabetical order breaks the tie."""
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    chunks = [
        _make_chunk("doc-z", 0.75),
        _make_chunk("doc-a", 0.75),
    ]
    monkeypatch.setattr(tool, "_retrieve", _fake_retrieve(chunks))

    out = tool.run({"query": "tiebreak"})

    cid_map = {c["source_id"]: c["citation_id"] for c in out["citations"]}
    assert cid_map["doc-a"] == "C1"
    assert cid_map["doc-z"] == "C2"


def test_same_source_shares_citation_id(monkeypatch):
    """Multiple chunks from the same source share one citation_id."""
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    chunks = [
        _make_chunk("doc-x", 0.85, span_start=0),
        _make_chunk("doc-x", 0.80, span_start=100),
    ]
    monkeypatch.setattr(tool, "_retrieve", _fake_retrieve(chunks))

    out = tool.run({"query": "multi-chunk"})

    assert out["total_chunks"] == 2
    assert len(out["citations"]) == 1
    assert out["chunks"][0]["citation_id"] == "C1"
    assert out["chunks"][1]["citation_id"] == "C1"


def test_empty_results(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    monkeypatch.setattr(tool, "_retrieve", _fake_retrieve([]))

    out = tool.run({"query": "empty"})

    assert out["total_chunks"] == 0
    assert out["chunks"] == []
    assert out["citations"] == []


def test_schema_rejects_missing_query(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    with pytest.raises(ValueError):
        tool.run({})


def test_schema_rejects_top_k_out_of_range(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    with pytest.raises(ValueError):
        tool.run({"query": "test", "top_k": 100})


def test_schema_rejects_extra_fields(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    monkeypatch.setattr(tool, "_retrieve", _fake_retrieve([]))
    with pytest.raises(ValueError):
        tool.run({"query": "test", "unknown_field": "oops"})
