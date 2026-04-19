"""API routes for the Model Registry.

Endpoints:
- GET  /api/providers                              -> enabled providers
- GET  /api/providers/{provider}/models             -> cached model list (ETag support)
- POST /api/providers/{provider}/models/refresh     -> force refresh
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.model_registry.schemas import ProviderModels
from agent_compiler.model_registry.service import (
    ModelRegistryService,
    compute_credential_fingerprint,
    compute_etag,
)
from agent_compiler.models.credentials import CredentialProvider
from agent_compiler.services.credential_service import (
    CredentialService,
    CredentialResolutionError,
)
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/providers", tags=["providers"])

SUPPORTED_PROVIDERS = ["openai", "anthropic", "gemini"]


def _validate_provider(provider: str) -> str:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    return provider


async def _resolve_key(
    session: AsyncSession,
    provider: str,
    project_id: str,
) -> str:
    """Resolve API key for the provider using existing credential service."""
    cred_provider = CredentialProvider(provider)
    svc = CredentialService(session)
    try:
        return await svc.resolve_credential(
            provider=cred_provider,
            project_id=project_id,
        )
    except CredentialResolutionError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())


# ── GET /api/providers ──────────────────────────────────────────────

@router.get("")
async def list_providers() -> dict[str, Any]:
    """Return the list of supported providers."""
    return {
        "providers": [
            {"id": "openai", "label": "OpenAI"},
            {"id": "anthropic", "label": "Anthropic (Claude)"},
            {"id": "gemini", "label": "Google Gemini"},
        ]
    }


# ── GET /api/providers/{provider}/models ────────────────────────────

@router.get("/{provider}/models")
async def get_provider_models(
    provider: str,
    response: Response,
    project_id: str = Query(..., description="Project ID for credential lookup"),
    region: str | None = Query(None, description="Optional region"),
    if_none_match: str | None = Header(None, alias="if-none-match"),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Get cached model list for a provider.

    Supports ETag / If-None-Match for 304 responses.
    """
    _validate_provider(provider)
    api_key = await _resolve_key(session, provider, project_id)

    registry = ModelRegistryService(session)
    result = await registry.get_models(
        provider=provider,
        api_key=api_key,
        project_id=project_id,
        region=region,
    )

    etag = compute_etag(result.models)

    # Check If-None-Match
    if if_none_match and if_none_match.strip('"') == etag:
        response.status_code = 304
        response.headers["ETag"] = f'"{etag}"'
        response.headers["Cache-Control"] = "private, max-age=0"
        return Response(status_code=304, headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "private, max-age=0",
        })

    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "private, max-age=0"

    return result.model_dump()


# ── POST /api/providers/{provider}/models/refresh ───────────────────

@router.post("/{provider}/models/refresh")
async def refresh_provider_models(
    provider: str,
    response: Response,
    project_id: str = Query(..., description="Project ID for credential lookup"),
    region: str | None = Query(None, description="Optional region"),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Force-refresh model list from provider (synchronous)."""
    _validate_provider(provider)
    api_key = await _resolve_key(session, provider, project_id)

    registry = ModelRegistryService(session)
    try:
        result = await registry.get_models(
            provider=provider,
            api_key=api_key,
            project_id=project_id,
            region=region,
            force_refresh=True,
        )
    except Exception as e:
        logger.error(f"Provider refresh failed: {provider} -> {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch models from {provider}: {type(e).__name__}",
        )

    etag = compute_etag(result.models)
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "private, max-age=0"

    return result.model_dump()
