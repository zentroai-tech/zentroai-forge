"""Logical migration helpers for existing IR v2 payloads to v2.1 defaults."""

from __future__ import annotations

from agent_compiler.models.ir_v2 import FlowIRv2
from agent_compiler.models.ir_v2_1_defaults import normalize_flow_v21_defaults


def migrate_v2_to_v2_1_defaults(ir: FlowIRv2) -> FlowIRv2:
    """Hydrate optional v2.1 fields while keeping ir_version='2'."""
    return normalize_flow_v21_defaults(ir)
