"""Credentials data model for storing encrypted provider API keys.

Security Design:
- Secrets are encrypted at rest using Fernet (AES-128-CBC + HMAC)
- Master key from FORGE_MASTER_KEY environment variable
- Secrets NEVER returned in API responses after creation
- Resolution precedence: Project -> Workspace -> Env fallback (dev only)

Rotation-Ready Design Notes (v2):
- Add `key_version` column to track which master key version encrypted the secret
- Implement re-encryption job: decrypt with old key, encrypt with new key
- Support multiple active keys during rotation window
- Add `rotated_at` timestamp for audit trail
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlmodel import Field, SQLModel


class CredentialProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GITHUB = "github"


class CredentialScopeType(str, Enum):
    """Scope level for credential resolution."""

    WORKSPACE = "workspace"
    PROJECT = "project"


class CredentialTestStatus(str, Enum):
    """Status of credential test."""

    OK = "ok"
    FAIL = "fail"
    PENDING = "pending"


class Credential(SQLModel, table=True):
    """Encrypted credential storage for LLM providers.

    The secret is stored encrypted and NEVER returned after creation.
    Only metadata is exposed via API responses.
    """

    __tablename__ = "credentials"

    id: str = Field(primary_key=True, description="UUID for the credential")
    provider: CredentialProvider = Field(index=True, description="LLM provider")
    scope_type: CredentialScopeType = Field(index=True, description="workspace or project")
    scope_id: str = Field(index=True, description="ID of the workspace or project")
    name: str | None = Field(default=None, description="Optional friendly name")

    # Encrypted secret - NEVER expose in API responses
    secret_ciphertext: str = Field(description="Fernet-encrypted API key")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Test status tracking
    last_tested_at: datetime | None = Field(default=None)
    last_test_status: CredentialTestStatus | None = Field(default=None)
    last_test_error: str | None = Field(
        default=None,
        description="Truncated error message (max 500 chars)",
    )

    # Future: key_version for rotation support
    # key_version: int = Field(default=1, description="Master key version used for encryption")

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert to metadata-only dict (no secrets)."""
        return {
            "id": self.id,
            "provider": self.provider.value,
            "scope_type": self.scope_type.value,
            "scope_id": self.scope_id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_tested_at": self.last_tested_at.isoformat() if self.last_tested_at else None,
            "last_test_status": self.last_test_status.value if self.last_test_status else None,
            "last_test_error": self.last_test_error,
        }


# =============================================================================
# Pydantic Schemas for API (metadata only - no secrets in responses)
# =============================================================================


class CredentialCreate(SQLModel):
    """Request schema for creating a credential."""

    provider: CredentialProvider
    scope_type: CredentialScopeType
    scope_id: str
    name: str | None = None
    secret: str = Field(description="The API key (will be encrypted, never returned)")


class CredentialUpdate(SQLModel):
    """Request schema for updating a credential."""

    name: str | None = None
    secret: str | None = Field(
        default=None,
        description="New API key (will replace existing, never returned)",
    )


class CredentialMetadataResponse(SQLModel):
    """Response schema - metadata only, NO secrets."""

    id: str
    provider: str
    scope_type: str
    scope_id: str
    name: str | None
    created_at: str
    updated_at: str
    last_tested_at: str | None
    last_test_status: str | None
    last_test_error: str | None


class CredentialTestResponse(SQLModel):
    """Response schema for credential test."""

    id: str
    provider: str
    status: str
    tested_at: str
    error: str | None = None


class CredentialResolutionError(SQLModel):
    """Structured error for missing credentials."""

    provider: str
    scopes_checked: list[str]
    message: str
