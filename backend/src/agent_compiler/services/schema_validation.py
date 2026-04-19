"""Schema validation helpers for v2.1 handoff/tool contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from agent_compiler.models.ir import SchemaKind, SchemaRef


class SchemaValidationError(RuntimeError):
    """Raised when runtime payload violates a declared schema."""

    def __init__(self, message: str):
        super().__init__(message)


def _load_json_schema(ref: str) -> dict[str, Any]:
    path = Path(ref)
    if not path.exists():
        raise SchemaValidationError(f"Schema ref not found: {ref}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"Invalid JSON schema in {ref}: {exc}") from exc


def _resolve_schema_from_registry(
    ref: str,
    schema_contracts: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not ref.startswith("schema://"):
        return None
    schema_id = ref.replace("schema://", "", 1).strip()
    if not schema_id:
        raise SchemaValidationError("Invalid schema ref: missing schema id")
    registry = schema_contracts or {}
    schema_obj = registry.get(schema_id)
    if schema_obj is None:
        raise SchemaValidationError(f"Schema id not found in flow resources: {schema_id}")
    if not isinstance(schema_obj, dict):
        raise SchemaValidationError(f"Schema id '{schema_id}' is not a valid JSON object")
    return schema_obj


def validate_against_schema_ref(
    payload: dict[str, Any],
    schema_ref: SchemaRef | None,
    *,
    schema_contracts: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Validate payload against schema ref with lightweight checks."""
    if schema_ref is None:
        return

    if schema_ref.kind == SchemaKind.JSON_SCHEMA:
        schema = _resolve_schema_from_registry(schema_ref.ref, schema_contracts) or _load_json_schema(schema_ref.ref)
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = [k for k in required if k not in payload]
            if missing:
                raise SchemaValidationError(f"Missing required keys: {missing}")
        return

    if schema_ref.kind == SchemaKind.PYDANTIC:
        # MVP: accept known symbolic refs, fail-fast unknown.
        if "." not in schema_ref.ref:
            raise SchemaValidationError(
                f"Invalid pydantic schema ref '{schema_ref.ref}'. Expected module.ClassName"
            )
        return

    if schema_ref.kind == SchemaKind.ZOD:
        # Runtime backend cannot execute zod directly; require explicit exported JSON schema path.
        raise SchemaValidationError(
            "Zod schema refs are not directly executable in backend runtime. Use json_schema ref."
        )

    raise SchemaValidationError(f"Unsupported schema kind: {schema_ref.kind}")


def validate_payload_or_raise(
    payload: dict[str, Any],
    schema_ref: SchemaRef | None,
    *,
    soft_fail: bool,
    schema_contracts: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    """Validate payload and optionally soft-fail returning warning text."""
    try:
        validate_against_schema_ref(payload, schema_ref, schema_contracts=schema_contracts)
        return None
    except (SchemaValidationError, ValidationError) as exc:
        if soft_fail:
            return str(exc)
        raise SchemaValidationError(str(exc)) from exc
