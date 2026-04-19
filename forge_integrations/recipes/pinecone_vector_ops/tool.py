"""Pinecone vector database operations: ensure_index, upsert, query, delete.

Exposes a single ``run(args)`` entry point that dispatches on ``args["operation"]``.

Operations
----------
- ``ensure_collection`` — create index if it does not exist (serverless by default).
- ``upsert``            — insert or update vectors.
- ``query``             — nearest-neighbour search with optional metadata filter.
- ``delete``            — delete vectors by ID.

Environment variables
---------------------
- ``PINECONE_API_KEY``         (required)
- ``PINECONE_INDEX``           (required for upsert/query/delete if not in args)
- ``PINECONE_HOST``            (optional) direct index host URL for lower latency
- ``PINECONE_TIMEOUT_SECONDS`` (optional, default ``15``)
- ``PINECONE_CLOUD``           (optional, default ``aws``) for ensure_collection
- ``PINECONE_CLOUD_REGION``    (optional, default ``us-east-1``) for ensure_collection

Notes
-----
Pinecone serverless indexes cannot be resized after creation; ``ensure_collection``
is a no-op if the index already exists.  For pod-based indexes, create the index
manually via the Pinecone console and set ``PINECONE_INDEX`` + ``PINECONE_HOST``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from forge_integrations.shared.env import require_env
from forge_integrations.shared.schemas import load_schema, validate_payload

_SCHEMAS = Path(__file__).resolve().parent.parent.parent / "shared" / "schemas"
_ENSURE_SCHEMA = load_schema(_SCHEMAS / "vector_ensure_collection.input.json")
_UPSERT_SCHEMA = load_schema(_SCHEMAS / "vector_upsert.input.json")
_QUERY_IN_SCHEMA = load_schema(_SCHEMAS / "vector_query.input.json")
_QUERY_OUT_SCHEMA = load_schema(_SCHEMAS / "vector_query.output.json")
_DELETE_SCHEMA = load_schema(_SCHEMAS / "vector_delete.input.json")

_DISTANCE_TO_METRIC = {
    "cosine": "cosine",
    "euclidean": "euclidean",
    "dot": "dotproduct",
}


def _get_client():
    """Create and return a Pinecone client.  Import is lazy so tests can mock this.

    Env-var check runs *before* the SDK import so that missing configuration
    raises a clear error even when pinecone-client is not installed.
    """
    api_key = require_env("PINECONE_API_KEY")
    try:
        from pinecone import Pinecone  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "pinecone package is required for pinecone_vector_ops. "
            "Install with: pip install pinecone-client"
        ) from exc
    return Pinecone(api_key=api_key)


def _get_index(client, index_name: str):
    """Return an Index object for the given index name."""
    host = os.environ.get("PINECONE_HOST") or None
    if host:
        return client.Index(index_name, host=host)
    return client.Index(index_name)


def _resolve_index_name(args: dict[str, Any]) -> str:
    """Resolve index name from args['collection'] with fallback to PINECONE_INDEX env."""
    collection = str(args.get("collection") or "").strip()
    if collection:
        return collection
    return require_env("PINECONE_INDEX")


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------


def _ensure_collection(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_ENSURE_SCHEMA, payload=args, context="pinecone ensure_collection input")
    client = _get_client()

    index_name = str(args["collection"])
    size = int(args["size"])
    distance_key = str(args.get("distance", "cosine")).lower()
    metric = _DISTANCE_TO_METRIC.get(distance_key, "cosine")

    try:
        from pinecone import ServerlessSpec  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("pinecone ServerlessSpec not available — upgrade pinecone package") from exc

    # List existing indexes
    index_list = client.list_indexes()
    try:
        existing = {idx.name for idx in index_list.indexes}
    except AttributeError:
        # Older SDK versions return a list directly
        existing = {idx["name"] for idx in (index_list or [])}

    created = False
    if index_name not in existing:
        cloud = os.environ.get("PINECONE_CLOUD", "aws")
        region = os.environ.get("PINECONE_CLOUD_REGION", "us-east-1")
        client.create_index(
            name=index_name,
            dimension=size,
            metric=metric,
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
        created = True

    return {"ok": True, "collection": index_name, "created": created}


def _upsert(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_UPSERT_SCHEMA, payload=args, context="pinecone upsert input")
    client = _get_client()
    index_name = _resolve_index_name(args)
    index = _get_index(client, index_name)

    vectors = [
        {
            "id": str(p["id"]),
            "values": list(p["vector"]),
            "metadata": dict(p.get("payload") or {}),
        }
        for p in args["points"]
    ]
    index.upsert(vectors=vectors)
    return {"ok": True, "collection": index_name, "upserted": len(vectors)}


def _query(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_QUERY_IN_SCHEMA, payload=args, context="pinecone query input")
    client = _get_client()
    index_name = _resolve_index_name(args)
    index = _get_index(client, index_name)

    vector = list(args["vector"])
    top_k = int(args.get("top_k", 10) or 10)
    with_payload = bool(args.get("with_payload", True))
    filter_dict = args.get("filter") or None
    score_threshold = args.get("score_threshold")

    query_kwargs: dict[str, Any] = {
        "vector": vector,
        "top_k": top_k,
        "include_metadata": with_payload,
        "include_values": False,
    }
    if filter_dict:
        query_kwargs["filter"] = filter_dict

    result = index.query(**query_kwargs)

    # Handle both dict-style (older SDK) and object-style (newer SDK) responses.
    raw_matches = result.get("matches", []) if isinstance(result, dict) else getattr(result, "matches", [])

    matches = []
    for m in raw_matches:
        if isinstance(m, dict):
            mid, mscore, mpayload = m.get("id", ""), m.get("score", 0.0), m.get("metadata") or {}
        else:
            mid = getattr(m, "id", "")
            mscore = getattr(m, "score", 0.0)
            mpayload = dict(getattr(m, "metadata", None) or {})

        if score_threshold is not None and float(mscore) < float(score_threshold):
            continue
        matches.append({"id": str(mid), "score": float(mscore), "payload": mpayload})

    output: dict[str, Any] = {"matches": matches}
    validate_payload(schema=_QUERY_OUT_SCHEMA, payload=output, context="pinecone query output")
    return output


def _delete(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_DELETE_SCHEMA, payload=args, context="pinecone delete input")
    client = _get_client()
    index_name = _resolve_index_name(args)
    index = _get_index(client, index_name)

    ids = [str(i) for i in args["ids"]]
    index.delete(ids=ids)
    return {"ok": True, "collection": index_name, "deleted": len(ids)}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_VALID_OPS = frozenset(["ensure_collection", "upsert", "query", "delete"])


def run(args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a Pinecone operation.

    Args:
        args: must contain ``operation`` (one of ``ensure_collection``,
              ``upsert``, ``query``, ``delete``) plus operation-specific fields.

    Returns:
        Operation-specific result dict.
    """
    op = str(args.get("operation") or "")
    if op not in _VALID_OPS:
        raise RuntimeError(
            f"Unknown pinecone operation: {op!r}. "
            f"Must be one of: {sorted(_VALID_OPS)}"
        )
    # Strip the routing key so per-operation schema validation (additionalProperties: false)
    # does not fail on the 'operation' field.
    handler_args = {k: v for k, v in args.items() if k != "operation"}
    # Dispatch via globals() so monkeypatching of _query / _upsert / etc. works correctly.
    return globals()[f"_{op}"](handler_args)
