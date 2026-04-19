"""Credentials API endpoints.

All responses return metadata only - secrets are NEVER exposed.

Endpoints:
- POST   /api/credentials           Create a new credential
- GET    /api/credentials           List credentials (with filters)
- GET    /api/credentials/{id}      Get credential metadata
- PATCH  /api/credentials/{id}      Update credential (name/secret)
- DELETE /api/credentials/{id}      Delete a credential
- POST   /api/credentials/{id}/test Test credential validity

Security:
- Secrets encrypted at rest
- Secrets never in responses
- Secrets never logged
- TODO: Add rate limiting on test endpoint
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.models.credentials import (
    CredentialCreate,
    CredentialMetadataResponse,
    CredentialProvider,
    CredentialScopeType,
    CredentialTestResponse,
    CredentialUpdate,
)
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.credential_service import (
    CredentialService,
    CredentialNotFoundError,
)
from agent_compiler.services.encryption_service import (
    EncryptionError,
    MasterKeyNotConfiguredError,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


# =============================================================================
# Request/Response Models
# =============================================================================


class CreateCredentialRequest(BaseModel):
    """Request body for creating a credential."""

    provider: str = Field(
        description="Provider: 'openai', 'anthropic', or 'gemini'"
    )
    scope_type: str = Field(
        description="Scope type: 'workspace' or 'project'"
    )
    scope_id: str = Field(description="ID of the workspace or project")
    name: str | None = Field(default=None, description="Optional friendly name")
    secret: str = Field(description="The API key (will be encrypted)")


class UpdateCredentialRequest(BaseModel):
    """Request body for updating a credential."""

    name: str | None = Field(default=None, description="New name")
    secret: str | None = Field(
        default=None,
        description="New API key (replaces existing)",
    )


class CredentialListResponse(BaseModel):
    """Response for listing credentials."""

    credentials: list[CredentialMetadataResponse]
    total: int


# =============================================================================
# Helper Functions
# =============================================================================


def _validate_provider(provider_str: str) -> CredentialProvider:
    """Validate and convert provider string to enum."""
    try:
        return CredentialProvider(provider_str.lower())
    except ValueError:
        valid = [p.value for p in CredentialProvider]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider: {provider_str}. Must be one of: {valid}",
        )


def _validate_scope_type(scope_type_str: str) -> CredentialScopeType:
    """Validate and convert scope type string to enum."""
    try:
        return CredentialScopeType(scope_type_str.lower())
    except ValueError:
        valid = [s.value for s in CredentialScopeType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope_type: {scope_type_str}. Must be one of: {valid}",
        )


def _credential_to_response(credential) -> CredentialMetadataResponse:
    """Convert credential to metadata-only response."""
    return CredentialMetadataResponse(
        id=credential.id,
        provider=credential.provider.value,
        scope_type=credential.scope_type.value,
        scope_id=credential.scope_id,
        name=credential.name,
        created_at=credential.created_at.isoformat() if credential.created_at else "",
        updated_at=credential.updated_at.isoformat() if credential.updated_at else "",
        last_tested_at=(
            credential.last_tested_at.isoformat() if credential.last_tested_at else None
        ),
        last_test_status=(
            credential.last_test_status.value if credential.last_test_status else None
        ),
        last_test_error=credential.last_test_error,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=CredentialMetadataResponse, status_code=201)
async def create_credential(
    request: CreateCredentialRequest,
    session: AsyncSession = Depends(get_session),
) -> CredentialMetadataResponse:
    """Create a new credential.

    The secret is encrypted and stored securely.
    The response contains metadata only - the secret is NEVER returned.

    **Request Body:**
    ```json
    {
      "provider": "openai",
      "scope_type": "project",
      "scope_id": "my-project-id",
      "name": "Production OpenAI Key",
      "secret": "sk-..."
    }
    ```

    **Response:** Metadata only (no secret)
    """
    # Validate enums
    provider = _validate_provider(request.provider)
    scope_type = _validate_scope_type(request.scope_type)

    # Create the credential data
    create_data = CredentialCreate(
        provider=provider,
        scope_type=scope_type,
        scope_id=request.scope_id,
        name=request.name,
        secret=request.secret,
    )

    service = CredentialService(session)

    try:
        credential = await service.create_credential(create_data)
        return _credential_to_response(credential)
    except MasterKeyNotConfiguredError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        )
    except EncryptionError as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to encrypt credential. Please contact support.",
        )


@router.get("", response_model=CredentialListResponse)
async def list_credentials(
    scope_type: str | None = Query(default=None, description="Filter by scope type"),
    scope_id: str | None = Query(default=None, description="Filter by scope ID"),
    provider: str | None = Query(default=None, description="Filter by provider"),
    session: AsyncSession = Depends(get_session),
) -> CredentialListResponse:
    """List credentials with optional filters.

    Returns metadata only - secrets are NEVER included.

    **Query Parameters:**
    - `scope_type`: Filter by 'workspace' or 'project'
    - `scope_id`: Filter by specific workspace/project ID
    - `provider`: Filter by 'openai', 'anthropic', or 'gemini'

    **Example:**
    ```
    GET /api/credentials?scope_type=project&scope_id=my-project&provider=openai
    ```
    """
    # Validate optional filters
    scope_type_enum = None
    if scope_type:
        scope_type_enum = _validate_scope_type(scope_type)

    provider_enum = None
    if provider:
        provider_enum = _validate_provider(provider)

    service = CredentialService(session)
    credentials = await service.list_credentials(
        scope_type=scope_type_enum,
        scope_id=scope_id,
        provider=provider_enum,
    )

    return CredentialListResponse(
        credentials=[_credential_to_response(c) for c in credentials],
        total=len(credentials),
    )


@router.get("/{credential_id}", response_model=CredentialMetadataResponse)
async def get_credential(
    credential_id: str,
    session: AsyncSession = Depends(get_session),
) -> CredentialMetadataResponse:
    """Get a credential by ID.

    Returns metadata only - the secret is NEVER included.
    """
    service = CredentialService(session)
    credential = await service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=404,
            detail=f"Credential not found: {credential_id}",
        )

    return _credential_to_response(credential)


@router.patch("/{credential_id}", response_model=CredentialMetadataResponse)
async def update_credential(
    credential_id: str,
    request: UpdateCredentialRequest,
    session: AsyncSession = Depends(get_session),
) -> CredentialMetadataResponse:
    """Update a credential's name and/or secret.

    If a new secret is provided, it replaces the existing one.
    The test status is reset when the secret changes.

    **Request Body:**
    ```json
    {
      "name": "New Name",
      "secret": "sk-new-key..."
    }
    ```

    **Response:** Updated metadata (no secret)
    """
    service = CredentialService(session)

    update_data = CredentialUpdate(
        name=request.name,
        secret=request.secret,
    )

    try:
        credential = await service.update_credential(credential_id, update_data)
        return _credential_to_response(credential)
    except CredentialNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Credential not found: {credential_id}",
        )
    except EncryptionError:
        raise HTTPException(
            status_code=500,
            detail="Failed to encrypt credential. Please contact support.",
        )


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a credential.

    This permanently removes the encrypted secret.
    """
    service = CredentialService(session)
    deleted = await service.delete_credential(credential_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Credential not found: {credential_id}",
        )


@router.post("/{credential_id}/test", response_model=CredentialTestResponse)
async def test_credential(
    credential_id: str,
    session: AsyncSession = Depends(get_session),
) -> CredentialTestResponse:
    """Test a credential by making a minimal API request.

    This verifies the API key is valid and has basic access.

    **Test behavior by provider:**
    - OpenAI: Lists models
    - Anthropic: Small message request
    - Gemini: Lists models

    **Response:**
    ```json
    {
      "id": "credential-uuid",
      "provider": "openai",
      "status": "ok",
      "tested_at": "2024-01-01T00:00:00Z",
      "error": null
    }
    ```

    **Note:** The test status and timestamp are persisted.

    TODO: Add rate limiting to prevent abuse.
    """
    service = CredentialService(session)

    try:
        result = await service.test_credential(credential_id)
        return CredentialTestResponse(
            id=result["id"],
            provider=result["provider"],
            status=result["status"],
            tested_at=result["tested_at"],
            error=result.get("error"),
        )
    except CredentialNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Credential not found: {credential_id}",
        )
    except EncryptionError:
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt credential for testing.",
        )


# =============================================================================
# Resolution Endpoint (for debugging/info)
# =============================================================================


class CredentialResolutionInfoResponse(BaseModel):
    """Response showing credential resolution precedence."""

    provider: str
    resolution_order: list[str]
    env_fallback_var: str
    hint: str


@router.get("/info/resolution/{provider}")
async def get_resolution_info(
    provider: str,
) -> CredentialResolutionInfoResponse:
    """Get information about how credentials are resolved for a provider.

    This is informational only - it doesn't reveal any actual credentials.
    """
    provider_enum = _validate_provider(provider)

    env_vars = {
        CredentialProvider.OPENAI: "OPENAI_API_KEY",
        CredentialProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        CredentialProvider.GEMINI: "GOOGLE_API_KEY",
    }

    return CredentialResolutionInfoResponse(
        provider=provider_enum.value,
        resolution_order=[
            "1. Project-level credential (scope_type=project)",
            "2. Workspace-level credential (scope_type=workspace)",
            f"3. Environment variable: {env_vars[provider_enum]} (dev fallback)",
        ],
        env_fallback_var=env_vars[provider_enum],
        hint=(
            f"Create a credential with POST /api/credentials or set "
            f"{env_vars[provider_enum]} environment variable."
        ),
    )
