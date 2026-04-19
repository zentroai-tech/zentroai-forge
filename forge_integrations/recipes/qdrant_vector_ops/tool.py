"""Qdrant vector database operations: ensure_collection, upsert, query, delete.

Exposes a single ``run(args)`` entry point that dispatches on ``args["operation"]``.

Operations
----------
- ``ensure_collection`` — create collection if it does not exist.
- ``upsert``            — insert or update points.
- ``query``             — nearest-neighbour search with optional filter.
- ``delete``            — delete points by ID.

Environment variables
---------------------
- ``QDRANT_URL``             (required) e.g. ``https://my-cluster.qdrant.tech``
- ``QDRANT_API_KEY``         (optional) cloud API key
- ``QDRANT_TIMEOUT_SECONDS`` (optional, default ``15``)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from forge_integrations.shared.env import require_env
from forge_integrations.shared.schemas import load_schema, validate_payload

_SCHEMAS = Path(__file__).resolve().parent.parent.parent / "shared" / "schemas"
_ENSURE_SCHEMA = load_schema(_SCHEMAS / "vector_ensure_collection.input.json")
_UPSERT_SCHEMA = load_schema(_SCHEMAS / "vector_upsert.input.json")
_QUERY_IN_SCHEMA = load_schema(_SCHEMAS / "vector_query.input.json")
_QUERY_OUT_SCHEMA = load_schema(_SCHEMAS / "vector_query.output.json")
_DELETE_SCHEMA = load_schema(_SCHEMAS / "vector_delete.input.json")

_DISTANCE_MAP = {
    "cosine": "Cosine",
    "euclidean": "Euclid",
    "dot": "Dot",
}


def _check_url_safety(url: str) -> None:
    """Enforce HTTPS for non-localhost Qdrant connections."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    is_local = host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")
    if scheme not in ("http", "https"):
        raise ValueError(f"Invalid scheme in QDRANT_URL: {scheme!r}. Use http or https.")
    if scheme == "http" and not is_local:
        raise PermissionError(
            f"QDRANT_URL must use HTTPS for non-localhost connections. Got: {url!r}"
        )


def _get_client():
    """Create and return a QdrantClient.  Import is lazy so tests can mock this.

    Env-var and URL-safety checks run *before* the SDK import so that missing
    configuration raises a clear error even when qdrant-client is not installed.
    """
    url = require_env("QDRANT_URL")
    _check_url_safety(url)
    api_key = os.environ.get("QDRANT_API_KEY") or None
    timeout = float(os.environ.get("QDRANT_TIMEOUT_SECONDS", "15") or "15")
    try:
        from qdrant_client import QdrantClient  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "qdrant-client is required for qdrant_vector_ops. "
            "Install with: pip install qdrant-client"
        ) from exc
    return QdrantClient(url=url, api_key=api_key, timeout=timeout)


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------


def _ensure_collection(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_ENSURE_SCHEMA, payload=args, context="qdrant ensure_collection input")
    client = _get_client()

    try:
        from qdrant_client.models import Distance, VectorParams  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("qdrant-client models not available") from exc

    collection = str(args["collection"])
    size = int(args["size"])
    distance_key = str(args.get("distance", "cosine")).lower()
    distance_name = _DISTANCE_MAP.get(distance_key, "Cosine")
    distance = Distance[distance_name]

    existing = {c.name for c in client.get_collections().collections}
    created = False
    if collection not in existing:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=size, distance=distance),
            on_disk_payload=bool(args.get("on_disk", False)),
        )
        created = True

    return {"ok": True, "collection": collection, "created": created}


def _upsert(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_UPSERT_SCHEMA, payload=args, context="qdrant upsert input")
    client = _get_client()

    try:
        from qdrant_client.models import PointStruct  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("qdrant-client models not available") from exc

    collection = str(args["collection"])
    points = [
        PointStruct(
            id=str(p["id"]),
            vector=list(p["vector"]),
            payload=dict(p.get("payload") or {}),
        )
        for p in args["points"]
    ]
    client.upsert(collection_name=collection, points=points, wait=True)
    return {"ok": True, "collection": collection, "upserted": len(points)}


def _query(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_QUERY_IN_SCHEMA, payload=args, context="qdrant query input")
    client = _get_client()

    collection = str(args["collection"])
    vector = list(args["vector"])
    top_k = int(args.get("top_k", 10) or 10)
    with_payload = bool(args.get("with_payload", True))
    score_threshold = args.get("score_threshold")
    filter_dict = args.get("filter") or None

    qdrant_filter = None
    if filter_dict:
        try:
            from qdrant_client.models import Filter  # noqa: PLC0415

            qdrant_filter = Filter(**filter_dict)
        except Exception:  # noqa: BLE001
            # Newer client versions may accept raw dicts; fall back gracefully.
            qdrant_filter = filter_dict  # type: ignore[assignment]

    search_kwargs: dict[str, Any] = {
        "collection_name": collection,
        "query_vector": vector,
        "limit": top_k,
        "with_payload": with_payload,
    }
    if score_threshold is not None:
        search_kwargs["score_threshold"] = float(score_threshold)
    if qdrant_filter is not None:
        search_kwargs["query_filter"] = qdrant_filter

    results = client.search(**search_kwargs)

    matches = [
        {
            "id": str(r.id),
            "score": float(r.score),
            "payload": dict(r.payload or {}),
        }
        for r in results
    ]
    output: dict[str, Any] = {"matches": matches}
    validate_payload(schema=_QUERY_OUT_SCHEMA, payload=output, context="qdrant query output")
    return output


def _delete(args: dict[str, Any]) -> dict[str, Any]:
    validate_payload(schema=_DELETE_SCHEMA, payload=args, context="qdrant delete input")
    client = _get_client()

    try:
        from qdrant_client.models import PointIdsList  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("qdrant-client models not available") from exc

    collection = str(args["collection"])
    ids = [str(i) for i in args["ids"]]
    client.delete(
        collection_name=collection,
        points_selector=PointIdsList(points=ids),
        wait=True,
    )
    return {"ok": True, "collection": collection, "deleted": len(ids)}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_VALID_OPS = frozenset(["ensure_collection", "upsert", "query", "delete"])


def run(args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a Qdrant operation.

    Args:
        args: must contain ``operation`` (one of ``ensure_collection``,
              ``upsert``, ``query``, ``delete``) plus operation-specific fields.

    Returns:
        Operation-specific result dict.
    """
    op = str(args.get("operation") or "")
    if op not in _VALID_OPS:
        raise RuntimeError(
            f"Unknown qdrant operation: {op!r}. "
            f"Must be one of: {sorted(_VALID_OPS)}"
        )
    # Strip the routing key so per-operation schema validation (additionalProperties: false)
    # does not fail on the 'operation' field.
    handler_args = {k: v for k, v in args.items() if k != "operation"}
    # Dispatch via globals() so monkeypatching of _query / _upsert / etc. works correctly:
    # _OPERATIONS dict would capture function references at import time and bypass patches.
    return globals()[f"_{op}"](handler_args)
