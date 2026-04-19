"""RAG retriever with deterministic citation IDs (C1..Cn).

Calls a configurable RAG backend, assigns a deterministic [Cn] citation ID
to each unique source, deduplicates into a citations list, and enforces a
per-chunk byte cap so oversized chunks cannot flood the context window.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from forge_integrations.shared.env import require_env
from forge_integrations.shared.http import request_json
from forge_integrations.shared.schemas import load_schema, validate_payload

_DIR = Path(__file__).resolve().parent
_INPUT_SCHEMA = load_schema(_DIR / "schemas" / "rag_retriever_citations.input.json")
_OUTPUT_SCHEMA = load_schema(_DIR / "schemas" / "rag_retriever_citations.output.json")

# Hard cap: truncate chunk text at this many bytes to protect the context window.
_MAX_CHUNK_BYTES = 8_192  # 8 KB


def _retrieve(query: str, top_k: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Call the configured RAG backend and return raw chunks."""
    backend_url = require_env("RAG_BACKEND_URL")
    timeout_s = float(os.environ.get("RAG_REQUEST_TIMEOUT_S", "15") or "15")
    payload: dict[str, Any] = {"query": query, "top_k": top_k}
    if filters:
        payload["filters"] = filters
    response = request_json(
        method="POST",
        url=backend_url,
        json_body=payload,
        timeout_s=timeout_s,
    )
    chunks = response.get("chunks") or []
    if not isinstance(chunks, list):
        raise RuntimeError("RAG backend returned invalid chunks (expected list)")
    return chunks


def _sanitize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    """Enforce max chunk byte size and normalise field types."""
    text = str(chunk.get("text") or "")
    encoded = text.encode("utf-8")
    if len(encoded) > _MAX_CHUNK_BYTES:
        text = encoded[:_MAX_CHUNK_BYTES].decode("utf-8", errors="ignore")

    src = chunk.get("source") or {}
    span = src.get("span") or {}
    return {
        "text": text,
        "score": float(chunk.get("score", 0.0)),
        "source": {
            "source_id": str(src.get("source_id", "")),
            "title": str(src.get("title", "")),
            "url": str(src.get("url", "")),
            "span": {
                "start": int(span.get("start", 0)),
                "end": int(span.get("end", 0)),
            },
        },
    }


def _assign_citation_ids(
    raw_chunks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Assign deterministic C1..Cn IDs and deduplicate citations by source.

    Sort order: score descending, then source_id ascending, then span.start
    ascending.  The first unique source encountered in this order receives C1,
    the second C2, etc.  Chunks from the same source share a citation_id.
    """

    def _sort_key(c: dict[str, Any]) -> tuple[float, str, int]:
        src = c.get("source") or {}
        span = src.get("span") or {}
        return (
            -float(c.get("score", 0.0)),
            str(src.get("source_id", "")),
            int(span.get("start", 0)),
        )

    sorted_chunks = sorted(raw_chunks, key=_sort_key)
    source_to_cid: dict[str, str] = {}
    counter = 1
    citations: list[dict[str, Any]] = []

    for chunk in sorted_chunks:
        src = chunk.get("source") or {}
        source_id = str(src.get("source_id", ""))
        if source_id not in source_to_cid:
            cid = f"C{counter}"
            counter += 1
            source_to_cid[source_id] = cid
            citations.append(
                {
                    "citation_id": cid,
                    "source_id": source_id,
                    "title": str(src.get("title", "")),
                    "url": str(src.get("url", "")),
                }
            )
        chunk["citation_id"] = source_to_cid[source_id]

    return sorted_chunks, citations


def run(args: dict[str, Any]) -> dict[str, Any]:
    """Retrieve top-k chunks and return with deterministic C1..Cn citation IDs."""
    validate_payload(
        schema=_INPUT_SCHEMA,
        payload=args,
        context="rag_retriever_citations input",
    )

    query = str(args["query"])
    top_k = int(args.get("top_k", 8) or 8)
    filters = dict(args.get("filters") or {})

    raw_chunks = _retrieve(query, top_k, filters)
    sanitized = [_sanitize_chunk(c) for c in raw_chunks]
    chunks, citations = _assign_citation_ids(sanitized)

    output: dict[str, Any] = {
        "query": query,
        "chunks": chunks,
        "citations": citations,
        "total_chunks": len(chunks),
    }
    validate_payload(
        schema=_OUTPUT_SCHEMA,
        payload=output,
        context="rag_retriever_citations output",
    )
    return output
