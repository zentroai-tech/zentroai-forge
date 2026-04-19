"""Normalized schemas for model registry responses."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ModelInfo(BaseModel):
    """A single model from a provider."""

    id: str
    label: str
    status: Literal["available", "unavailable"] = "available"
    updated_at: str  # ISO 8601


class ProviderModels(BaseModel):
    """Normalized response for a provider's model list."""

    provider: Literal["openai", "anthropic", "gemini"]
    models: list[ModelInfo]
    warning: str | None = None


def model_id_to_label(model_id: str) -> str:
    """Derive a human-readable label from a model ID.

    Examples:
        gpt-4o-mini -> GPT 4o Mini
        claude-3-5-sonnet-20241022 -> Claude 3 5 Sonnet 20241022
        gemini-2.0-flash -> Gemini 2.0 Flash
    """
    # Replace separators with spaces
    label = model_id.replace("-", " ").replace("_", " ").replace(".", ".")
    # Title-case each word, but keep version numbers as-is
    parts = label.split()
    result = []
    for part in parts:
        # Keep pure numbers or version-like tokens as-is
        if part.replace(".", "").isdigit():
            result.append(part)
        else:
            result.append(part.capitalize())
    return " ".join(result)
