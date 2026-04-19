"""Model Registry Service - persistent cache + SWR + single-flight refresh.

Caching strategy:
- BACKEND_TTL (24h): How long a cache entry is considered fresh.
- STALE_GRACE (7d): How long a stale entry can be served while refreshing in background.
- Single-flight: Only one refresh per cache key at a time (in-memory asyncio.Lock per key).

Cache flow:
1. Fresh (now < expires_at) -> return cached immediately.
2. Stale (expired but now < fetched_at + STALE_GRACE) -> return cached + trigger async refresh.
3. Miss (no cache or beyond stale grace) -> fetch synchronously, store, return.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session_context
from agent_compiler.model_registry.adapters import get_adapter
from agent_compiler.model_registry.schemas import ModelInfo, ProviderModels
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

# TTL defaults (seconds)
BACKEND_TTL = 24 * 3600  # 24 hours
STALE_GRACE = 7 * 24 * 3600  # 7 days

# In-memory locks for single-flight refresh (keyed by cache key)
_refresh_locks: dict[str, asyncio.Lock] = {}
_refresh_in_progress: set[str] = set()


def _make_cache_key(project_id: str, provider: str, fingerprint: str, region: str | None) -> str:
    """Create a string key for lock maps."""
    return f"{project_id}:{provider}:{fingerprint}:{region or ''}"


def compute_credential_fingerprint(api_key: str, project_id: str) -> str:
    """Compute a non-reversible fingerprint for cache keying.

    Uses HMAC-SHA256 with the project_id as context so the same key
    produces different fingerprints across projects.
    """
    return hmac.new(
        project_id.encode(),
        api_key.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


def compute_etag(models: list[ModelInfo]) -> str:
    """Compute an ETag from the normalized model list."""
    payload = json.dumps(
        [m.model_dump() for m in models],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class ModelRegistryService:
    """Service for fetching, caching, and serving LLM model lists."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_models(
        self,
        provider: str,
        api_key: str,
        project_id: str,
        region: str | None = None,
        force_refresh: bool = False,
    ) -> ProviderModels:
        """Get models for a provider, using cache + SWR.

        Args:
            provider: "openai", "anthropic", or "gemini"
            api_key: Decrypted API key (NOT stored in cache)
            project_id: For multi-tenant isolation
            region: Optional region qualifier
            force_refresh: If True, bypass cache and fetch fresh

        Returns:
            ProviderModels with normalized model list
        """
        fingerprint = compute_credential_fingerprint(api_key, project_id)
        cache_key = _make_cache_key(project_id, provider, fingerprint, region)

        if not force_refresh:
            cached = await self._get_cached(project_id, provider, fingerprint, region)
            if cached is not None:
                now = datetime.now(timezone.utc)
                expires_at = datetime.fromisoformat(cached["expires_at"])
                fetched_at = datetime.fromisoformat(cached["fetched_at"])
                stale_deadline = fetched_at + timedelta(seconds=STALE_GRACE)

                if now < expires_at:
                    # Fresh cache
                    models = [ModelInfo(**m) for m in json.loads(cached["payload_json"])]
                    return ProviderModels(provider=provider, models=models)

                if now < stale_deadline:
                    # Stale but within grace period - serve stale + trigger background refresh
                    models = [ModelInfo(**m) for m in json.loads(cached["payload_json"])]
                    self._schedule_refresh(
                        provider, api_key, project_id, fingerprint, region, cache_key
                    )
                    return ProviderModels(provider=provider, models=models)

        # No usable cache or force_refresh -> fetch synchronously
        return await self._fetch_and_store(
            provider, api_key, project_id, fingerprint, region, cache_key
        )

    async def _get_cached(
        self,
        project_id: str,
        provider: str,
        fingerprint: str,
        region: str | None,
    ) -> dict[str, Any] | None:
        """Look up cached entry from DB."""
        if region is None:
            stmt = text("""
                SELECT payload_json, etag, fetched_at, expires_at
                FROM model_cache
                WHERE project_id = :pid AND provider = :prov
                  AND credential_fingerprint = :fp AND region IS NULL
            """)
            params = {"pid": project_id, "prov": provider, "fp": fingerprint}
        else:
            stmt = text("""
                SELECT payload_json, etag, fetched_at, expires_at
                FROM model_cache
                WHERE project_id = :pid AND provider = :prov
                  AND credential_fingerprint = :fp AND region = :reg
            """)
            params = {"pid": project_id, "prov": provider, "fp": fingerprint, "reg": region}

        result = await self.session.execute(stmt, params)
        row = result.fetchone()
        if row is None:
            return None
        return {
            "payload_json": row[0],
            "etag": row[1],
            "fetched_at": row[2],
            "expires_at": row[3],
        }

    async def _fetch_and_store(
        self,
        provider: str,
        api_key: str,
        project_id: str,
        fingerprint: str,
        region: str | None,
        cache_key: str,
    ) -> ProviderModels:
        """Fetch from provider API and store in cache. Returns result or stale cache on failure."""
        adapter = get_adapter(provider)
        start = time.monotonic()
        warning: str | None = None

        try:
            result = await adapter.list_models(api_key)
            elapsed = time.monotonic() - start
            logger.info(
                f"model_registry.refresh provider={provider} "
                f"models={len(result.models)} latency={elapsed:.2f}s"
            )
        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error(
                f"model_registry.refresh_failed provider={provider} "
                f"error={type(e).__name__}: {e} latency={elapsed:.2f}s"
            )
            # Try to return stale cache
            cached = await self._get_cached(project_id, provider, fingerprint, region)
            if cached is not None:
                models = [ModelInfo(**m) for m in json.loads(cached["payload_json"])]
                return ProviderModels(
                    provider=provider,
                    models=models,
                    warning="provider_fetch_failed_using_cache",
                )
            # No cache at all -> raise
            raise

        # Store in DB
        await self._upsert_cache(
            project_id, provider, fingerprint, region, result.models
        )

        if warning:
            result.warning = warning
        return result

    async def _upsert_cache(
        self,
        project_id: str,
        provider: str,
        fingerprint: str,
        region: str | None,
        models: list[ModelInfo],
    ) -> None:
        """Insert or update the cache entry."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=BACKEND_TTL)
        payload = json.dumps([m.model_dump() for m in models], separators=(",", ":"))
        etag = compute_etag(models)

        # SQLite UPSERT
        await self.session.execute(
            text("""
                INSERT INTO model_cache (id, project_id, provider, credential_fingerprint,
                                         region, payload_json, etag, fetched_at, expires_at)
                VALUES (:id, :pid, :prov, :fp, :reg, :payload, :etag, :fetched, :expires)
                ON CONFLICT (project_id, provider, credential_fingerprint, region)
                DO UPDATE SET
                    payload_json = excluded.payload_json,
                    etag = excluded.etag,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
            """),
            {
                "id": str(uuid.uuid4()),
                "pid": project_id,
                "prov": provider,
                "fp": fingerprint,
                "reg": region,
                "payload": payload,
                "etag": etag,
                "fetched": now.isoformat(),
                "expires": expires.isoformat(),
            },
        )
        await self.session.commit()

    def _schedule_refresh(
        self,
        provider: str,
        api_key: str,
        project_id: str,
        fingerprint: str,
        region: str | None,
        cache_key: str,
    ) -> None:
        """Schedule a single-flight background refresh."""
        if cache_key in _refresh_in_progress:
            return  # Already refreshing

        async def _do_refresh() -> None:
            _refresh_in_progress.add(cache_key)
            try:
                async with get_session_context() as session:
                    svc = ModelRegistryService(session)
                    await svc._fetch_and_store(
                        provider, api_key, project_id, fingerprint, region, cache_key
                    )
            except Exception as e:
                logger.warning(f"model_registry.background_refresh_failed: {e}")
            finally:
                _refresh_in_progress.discard(cache_key)

        asyncio.get_event_loop().create_task(_do_refresh())

    async def get_etag(
        self,
        project_id: str,
        provider: str,
        api_key: str,
        region: str | None = None,
    ) -> str | None:
        """Get the current ETag for a cache entry."""
        fingerprint = compute_credential_fingerprint(api_key, project_id)
        cached = await self._get_cached(project_id, provider, fingerprint, region)
        return cached["etag"] if cached else None
