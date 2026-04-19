"""JSON schema load/validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema


def load_schema(path: Path) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError(f"Schema is not an object: {path}")
    return schema


def validate_payload(*, schema: dict[str, Any], payload: dict[str, Any], context: str) -> None:
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"{context} validation failed: {exc.message}") from exc

