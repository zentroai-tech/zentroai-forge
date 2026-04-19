"""Provider adapters for fetching model lists.

Each adapter normalizes the provider-specific response into ProviderModels.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone

import httpx

from agent_compiler.model_registry.schemas import (
    ModelInfo,
    ProviderModels,
    model_id_to_label,
)
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class BaseModelAdapter(abc.ABC):
    """Base class for provider model adapters."""

    provider: str

    @abc.abstractmethod
    async def list_models(self, api_key: str) -> ProviderModels:
        """Fetch and return normalized models from the provider."""


class OpenAIAdapter(BaseModelAdapter):
    """Adapter for OpenAI /v1/models."""

    provider = "openai"

    async def list_models(self, api_key: str) -> ProviderModels:
        now = datetime.now(timezone.utc).isoformat()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        models: list[ModelInfo] = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            # Skip internal/fine-tune snapshots
            if ":ft-" in model_id or model_id.startswith("ft:"):
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    label=model_id_to_label(model_id),
                    status="available",
                    updated_at=now,
                )
            )

        models.sort(key=lambda m: m.id)
        return ProviderModels(provider="openai", models=models)


class AnthropicAdapter(BaseModelAdapter):
    """Adapter for Anthropic /v1/models."""

    provider = "anthropic"

    async def list_models(self, api_key: str) -> ProviderModels:
        now = datetime.now(timezone.utc).isoformat()
        models: list[ModelInfo] = []

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Anthropic paginates with has_more / first_id / last_id
            url = "https://api.anthropic.com/v1/models?limit=100"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }

            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("data", []):
                    model_id = item.get("id", "")
                    display = item.get("display_name", "") or model_id_to_label(model_id)
                    models.append(
                        ModelInfo(
                            id=model_id,
                            label=display,
                            status="available",
                            updated_at=now,
                        )
                    )

                if data.get("has_more") and data.get("last_id"):
                    url = f"https://api.anthropic.com/v1/models?limit=100&after_id={data['last_id']}"
                else:
                    url = ""

        models.sort(key=lambda m: m.id)
        return ProviderModels(provider="anthropic", models=models)


class GeminiAdapter(BaseModelAdapter):
    """Adapter for Google Gemini /v1beta/models."""

    provider = "gemini"

    async def list_models(self, api_key: str) -> ProviderModels:
        now = datetime.now(timezone.utc).isoformat()
        models: list[ModelInfo] = []

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            url: str | None = (
                "https://generativelanguage.googleapis.com/v1beta/models"
            )
            while url:
                resp = await client.get(
                    url,
                    params={"key": api_key, "pageSize": 100},
                )
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("models", []):
                    # name comes as "models/gemini-2.0-flash"
                    full_name = item.get("name", "")
                    model_id = full_name.removeprefix("models/")
                    display = item.get("displayName", "") or model_id_to_label(model_id)

                    # Only include generative models
                    methods = item.get("supportedGenerationMethods", [])
                    if "generateContent" not in methods:
                        continue

                    models.append(
                        ModelInfo(
                            id=model_id,
                            label=display,
                            status="available",
                            updated_at=now,
                        )
                    )

                next_token = data.get("nextPageToken")
                if next_token:
                    url = "https://generativelanguage.googleapis.com/v1beta/models"
                    # pageToken handled via params in next iteration
                    resp_next = await client.get(
                        url,
                        params={"key": api_key, "pageSize": 100, "pageToken": next_token},
                    )
                    resp_next.raise_for_status()
                    data = resp_next.json()
                    for item in data.get("models", []):
                        full_name = item.get("name", "")
                        model_id = full_name.removeprefix("models/")
                        display = item.get("displayName", "") or model_id_to_label(model_id)
                        methods = item.get("supportedGenerationMethods", [])
                        if "generateContent" not in methods:
                            continue
                        models.append(
                            ModelInfo(
                                id=model_id,
                                label=display,
                                status="available",
                                updated_at=now,
                            )
                        )
                    url = None  # Stop after second page for safety
                else:
                    url = None

        models.sort(key=lambda m: m.id)
        return ProviderModels(provider="gemini", models=models)


_ADAPTERS: dict[str, BaseModelAdapter] = {
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
    "gemini": GeminiAdapter(),
}


def get_adapter(provider: str) -> BaseModelAdapter:
    """Get the adapter for a provider.

    Args:
        provider: One of "openai", "anthropic", "gemini"

    Raises:
        ValueError: If provider is unknown
    """
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError(f"Unknown provider: {provider}")
    return adapter
