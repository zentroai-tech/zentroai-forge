"""Provider-agnostic vector DB router.

Selects the backend (``qdrant`` or ``pinecone``) from the ``provider`` field
in the payload and delegates to the appropriate recipe tool.

Usage::

    from forge_integrations.shared.vector_router import (
        vector_ensure_collection,
        vector_upsert,
        vector_query,
        vector_delete,
    )

    result = vector_query({
        "provider": "qdrant",
        "collection": "documents",
        "vector": [0.1, 0.2, ...],
        "top_k": 5,
    })

The ``provider`` field is stripped before passing args to the underlying tool
so recipes do not need to handle it.
"""

from __future__ import annotations

from typing import Any

_SUPPORTED_PROVIDERS = ("qdrant", "pinecone")


def _resolve_tool(provider: str):
    """Import and return the provider-specific tool module."""
    if provider == "qdrant":
        from forge_integrations.recipes.qdrant_vector_ops import tool  # noqa: PLC0415

        return tool
    if provider == "pinecone":
        from forge_integrations.recipes.pinecone_vector_ops import tool  # noqa: PLC0415

        return tool
    raise RuntimeError(
        f"Unknown vector provider: {provider!r}. Must be one of: {list(_SUPPORTED_PROVIDERS)}"
    )


def _dispatch(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "").lower().strip()
    if not provider:
        raise RuntimeError(
            f"Missing 'provider' field in vector_router payload. "
            f"Must be one of: {list(_SUPPORTED_PROVIDERS)}"
        )
    tool = _resolve_tool(provider)
    # Strip provider key so the underlying recipe tool does not see unknown fields.
    args = {k: v for k, v in payload.items() if k != "provider"}
    args["operation"] = operation
    return tool.run(args)


def vector_ensure_collection(payload: dict[str, Any]) -> dict[str, Any]:
    """Create or verify a collection/index (provider-agnostic).

    Required payload fields: ``provider``, ``collection``, ``size``.
    Optional: ``distance`` (default ``cosine``), ``on_disk`` (Qdrant only).
    """
    return _dispatch("ensure_collection", payload)


def vector_upsert(payload: dict[str, Any]) -> dict[str, Any]:
    """Upsert vectors into a collection (provider-agnostic).

    Required payload fields: ``provider``, ``collection``, ``points``.
    Each point: ``{"id": str, "vector": list[float], "payload": dict}``.
    """
    return _dispatch("upsert", payload)


def vector_query(payload: dict[str, Any]) -> dict[str, Any]:
    """Query nearest neighbours (provider-agnostic).

    Required payload fields: ``provider``, ``collection``, ``vector``.
    Optional: ``top_k`` (default 10), ``filter``, ``with_payload``, ``score_threshold``.
    Returns ``{"matches": [{"id", "score", "payload"}, ...]}``.
    """
    return _dispatch("query", payload)


def vector_delete(payload: dict[str, Any]) -> dict[str, Any]:
    """Delete vectors by ID (provider-agnostic).

    Required payload fields: ``provider``, ``collection``, ``ids``.
    """
    return _dispatch("delete", payload)
