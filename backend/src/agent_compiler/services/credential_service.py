"""Credential management service.

Handles CRUD operations, credential resolution, and provider testing.

Resolution Precedence (for each provider):
1. Project credential (if scope_id matches flow's project)
2. Workspace credential (if scope_id matches flow's workspace)
3. Environment variable fallback (dev only):
   - OpenAI: OPENAI_API_KEY
   - Anthropic: ANTHROPIC_API_KEY
   - Gemini: GOOGLE_API_KEY
4. Structured 400 error with scopes checked

Security:
- Secrets are encrypted at rest
- Secrets NEVER returned in responses
- Logs use masked values only
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.credentials import (
    Credential,
    CredentialCreate,
    CredentialProvider,
    CredentialScopeType,
    CredentialTestStatus,
    CredentialUpdate,
)
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.encryption_service import (
    decrypt_secret,
    encrypt_secret,
    mask_secret,
    EncryptionError,
    MasterKeyNotConfiguredError,
)

logger = get_logger(__name__)


# Environment variable fallbacks (dev only)
ENV_FALLBACKS: dict[CredentialProvider, str] = {
    CredentialProvider.OPENAI: "OPENAI_API_KEY",
    CredentialProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    CredentialProvider.GEMINI: "GOOGLE_API_KEY",
    CredentialProvider.GITHUB: "GITHUB_TOKEN",
}


class CredentialNotFoundError(Exception):
    """Raised when a credential is not found."""

    pass


class CredentialResolutionError(Exception):
    """Raised when no credential can be resolved for a provider."""

    def __init__(
        self,
        provider: CredentialProvider,
        scopes_checked: list[str],
        message: str,
    ):
        self.provider = provider
        self.scopes_checked = scopes_checked
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "credential_not_found",
            "provider": self.provider.value,
            "scopes_checked": self.scopes_checked,
            "message": self.message,
        }


class CredentialService:
    """Service for managing encrypted credentials."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_credential(self, data: CredentialCreate) -> Credential:
        """Create a new credential with encrypted secret.

        Args:
            data: Credential creation data including plaintext secret

        Returns:
            Created credential (without secret in response)

        Raises:
            EncryptionError: If encryption fails
            MasterKeyNotConfiguredError: If master key not set
        """
        # Encrypt the secret
        ciphertext = encrypt_secret(data.secret)

        credential = Credential(
            id=str(uuid.uuid4()),
            provider=data.provider,
            scope_type=data.scope_type,
            scope_id=data.scope_id,
            name=data.name,
            secret_ciphertext=ciphertext,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self.session.add(credential)
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info(
            f"Created credential: provider={data.provider.value}, "
            f"scope={data.scope_type.value}/{data.scope_id}, "
            f"id={credential.id}"
        )

        return credential

    async def get_credential(self, credential_id: str) -> Credential | None:
        """Get a credential by ID (metadata only, no decryption)."""
        statement = select(Credential).where(Credential.id == credential_id)
        result = await self.session.exec(statement)
        return result.one_or_none()

    async def list_credentials(
        self,
        scope_type: CredentialScopeType | None = None,
        scope_id: str | None = None,
        provider: CredentialProvider | None = None,
    ) -> list[Credential]:
        """List credentials with optional filters (metadata only)."""
        statement = select(Credential)

        if scope_type:
            statement = statement.where(Credential.scope_type == scope_type)
        if scope_id:
            statement = statement.where(Credential.scope_id == scope_id)
        if provider:
            statement = statement.where(Credential.provider == provider)

        statement = statement.order_by(Credential.created_at.desc())

        result = await self.session.exec(statement)
        return list(result.all())

    async def update_credential(
        self,
        credential_id: str,
        data: CredentialUpdate,
    ) -> Credential:
        """Update a credential (name and/or secret).

        Args:
            credential_id: ID of credential to update
            data: Update data

        Returns:
            Updated credential (metadata only)

        Raises:
            CredentialNotFoundError: If credential not found
            EncryptionError: If encryption fails
        """
        credential = await self.get_credential(credential_id)
        if credential is None:
            raise CredentialNotFoundError(f"Credential not found: {credential_id}")

        if data.name is not None:
            credential.name = data.name

        if data.secret is not None:
            credential.secret_ciphertext = encrypt_secret(data.secret)
            # Reset test status when secret changes
            credential.last_tested_at = None
            credential.last_test_status = None
            credential.last_test_error = None

        credential.updated_at = datetime.now(timezone.utc)

        self.session.add(credential)
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info(f"Updated credential: id={credential_id}")

        return credential

    async def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential.

        Args:
            credential_id: ID of credential to delete

        Returns:
            True if deleted, False if not found
        """
        credential = await self.get_credential(credential_id)
        if credential is None:
            return False

        await self.session.delete(credential)
        await self.session.commit()

        logger.info(
            f"Deleted credential: id={credential_id}, "
            f"provider={credential.provider.value}"
        )

        return True

    async def resolve_credential(
        self,
        provider: CredentialProvider,
        project_id: str | None = None,
        workspace_id: str | None = None,
        allow_env_fallback: bool = True,
    ) -> str:
        """Resolve the API key for a provider using precedence rules.

        Resolution order:
        1. Project-level credential (if project_id provided)
        2. Workspace-level credential (if workspace_id provided)
        3. Environment variable fallback (if allow_env_fallback=True)

        Args:
            provider: The LLM provider
            project_id: Optional project ID for project-level lookup
            workspace_id: Optional workspace ID for workspace-level lookup
            allow_env_fallback: Whether to check env vars (dev mode)

        Returns:
            Decrypted API key

        Raises:
            CredentialResolutionError: If no credential found
            EncryptionError: If decryption fails
        """
        scopes_checked: list[str] = []

        # 1. Check project-level credential
        if project_id:
            scopes_checked.append(f"project:{project_id}")
            statement = select(Credential).where(
                Credential.provider == provider,
                Credential.scope_type == CredentialScopeType.PROJECT,
                Credential.scope_id == project_id,
            )
            result = await self.session.exec(statement)
            credential = result.one_or_none()

            if credential:
                logger.debug(
                    f"Resolved {provider.value} credential from project:{project_id}"
                )
                return decrypt_secret(credential.secret_ciphertext)

        # 2. Check workspace-level credential
        # If workspace_id is given, match exactly; otherwise search ANY workspace credential
        if workspace_id:
            scopes_checked.append(f"workspace:{workspace_id}")
            statement = select(Credential).where(
                Credential.provider == provider,
                Credential.scope_type == CredentialScopeType.WORKSPACE,
                Credential.scope_id == workspace_id,
            )
        else:
            scopes_checked.append("workspace:*")
            statement = select(Credential).where(
                Credential.provider == provider,
                Credential.scope_type == CredentialScopeType.WORKSPACE,
            )
        result = await self.session.exec(statement)
        credential = result.one_or_none()

        if credential:
            logger.debug(
                f"Resolved {provider.value} credential from "
                f"workspace:{credential.scope_id}"
            )
            return decrypt_secret(credential.secret_ciphertext)

        # 3. Environment variable fallback (dev only)
        if allow_env_fallback:
            env_var = ENV_FALLBACKS.get(provider)
            if env_var:
                scopes_checked.append(f"env:{env_var}")
                env_value = os.environ.get(env_var)
                if env_value:
                    logger.debug(
                        f"Resolved {provider.value} credential from env:{env_var}"
                    )
                    return env_value

        # No credential found
        raise CredentialResolutionError(
            provider=provider,
            scopes_checked=scopes_checked,
            message=(
                f"No {provider.value} API key found. "
                f"Checked: {', '.join(scopes_checked)}. "
                f"Please add a credential or set the {ENV_FALLBACKS.get(provider, 'API_KEY')} environment variable."
            ),
        )

    async def test_credential(self, credential_id: str) -> dict[str, Any]:
        """Test a credential by making a minimal API request.

        Args:
            credential_id: ID of credential to test

        Returns:
            Test result with status and timestamp

        Raises:
            CredentialNotFoundError: If credential not found
        """
        credential = await self.get_credential(credential_id)
        if credential is None:
            raise CredentialNotFoundError(f"Credential not found: {credential_id}")

        # Decrypt the secret for testing
        try:
            api_key = decrypt_secret(credential.secret_ciphertext)
        except EncryptionError as e:
            return await self._update_test_status(
                credential,
                CredentialTestStatus.FAIL,
                f"Decryption failed: {str(e)[:200]}",
            )

        # Test based on provider
        try:
            if credential.provider == CredentialProvider.OPENAI:
                await self._test_openai(api_key)
            elif credential.provider == CredentialProvider.ANTHROPIC:
                await self._test_anthropic(api_key)
            elif credential.provider == CredentialProvider.GEMINI:
                await self._test_gemini(api_key)
            elif credential.provider == CredentialProvider.GITHUB:
                await self._test_github(api_key)
            else:
                raise ValueError(f"Unknown provider: {credential.provider}")

            return await self._update_test_status(
                credential,
                CredentialTestStatus.OK,
                None,
            )

        except Exception as e:
            # Truncate and sanitize error message
            error_msg = str(e)[:500]
            # Remove any potential secret leakage
            if api_key and api_key in error_msg:
                error_msg = error_msg.replace(api_key, mask_secret(api_key))

            logger.warning(
                f"Credential test failed: id={credential_id}, "
                f"provider={credential.provider.value}, "
                f"error={error_msg[:100]}..."
            )

            return await self._update_test_status(
                credential,
                CredentialTestStatus.FAIL,
                error_msg,
            )

    async def _update_test_status(
        self,
        credential: Credential,
        status: CredentialTestStatus,
        error: str | None,
    ) -> dict[str, Any]:
        """Update credential test status and return result."""
        credential.last_tested_at = datetime.now(timezone.utc)
        credential.last_test_status = status
        credential.last_test_error = error

        self.session.add(credential)
        await self.session.commit()
        await self.session.refresh(credential)

        return {
            "id": credential.id,
            "provider": credential.provider.value,
            "status": status.value,
            "tested_at": credential.last_tested_at.isoformat(),
            "error": error,
        }

    async def _test_openai(self, api_key: str) -> None:
        """Test OpenAI API key with a minimal request."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key)
            # List models is a lightweight test
            await client.models.list()
            logger.debug("OpenAI credential test: OK")
        except ImportError:
            # If openai not installed, try with httpx
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                if response.status_code == 401:
                    raise ValueError("Invalid API key")
                response.raise_for_status()

    async def _test_anthropic(self, api_key: str) -> None:
        """Test Anthropic API key with a minimal request."""
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key)
            # Small message request
            await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "Hi"}],
            )
            logger.debug("Anthropic credential test: OK")
        except ImportError:
            # If anthropic not installed, try with httpx
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "Hi"}],
                    },
                    timeout=10.0,
                )
                if response.status_code == 401:
                    raise ValueError("Invalid API key")
                response.raise_for_status()

    async def _test_gemini(self, api_key: str) -> None:
        """Test Google Gemini API key with a minimal request."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            # List models is lightweight
            list(genai.list_models())
            logger.debug("Gemini credential test: OK")
        except ImportError:
            # If google-generativeai not installed, try with httpx
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://generativelanguage.googleapis.com/v1/models?key={api_key}",
                    timeout=10.0,
                )
                if response.status_code == 401 or response.status_code == 403:
                    raise ValueError("Invalid API key")
                response.raise_for_status()

    async def _test_github(self, token: str) -> None:
        """Test GitHub PAT by calling GET /user."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                timeout=10.0,
            )
            if response.status_code == 401:
                raise ValueError("Invalid GitHub token")
            response.raise_for_status()
            logger.debug("GitHub credential test: OK")


# =============================================================================
# Utility functions for runtime integration
# =============================================================================


async def resolve_provider_key(
    session: AsyncSession,
    provider: CredentialProvider,
    project_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    """Convenience function to resolve a provider API key.

    Args:
        session: Database session
        provider: The LLM provider
        project_id: Optional project ID
        workspace_id: Optional workspace ID

    Returns:
        The resolved API key

    Raises:
        CredentialResolutionError: If no credential found
    """
    service = CredentialService(session)
    return await service.resolve_credential(
        provider=provider,
        project_id=project_id,
        workspace_id=workspace_id,
    )
