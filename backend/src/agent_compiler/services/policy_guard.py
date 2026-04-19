"""Policy guard helpers for v2.1 runtime controls."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent_compiler.models.ir_v2 import PolicySpec
from agent_compiler.services.tool_security import is_tool_allowed


@dataclass
class GuardDecision:
    allowed: bool
    reason: str | None = None
    code: str | None = None


@dataclass
class AbstainResult:
    reason: str
    confidence: float


def sanitize_input(text: str, policy: PolicySpec) -> str:
    """Apply text sanitization policy."""
    if not policy.input_sanitization.enabled:
        return text
    value = text
    if policy.input_sanitization.strip_html:
        value = re.sub(r"<[^>]+>", " ", value)
    max_chars = policy.input_sanitization.max_input_chars
    if len(value) > max_chars:
        value = value[:max_chars]
    return value


def apply_redaction(text: str, policy: PolicySpec) -> str:
    """Apply redaction patterns to text."""
    if not policy.redaction.enabled or not policy.redaction.patterns:
        return text
    masked = text
    for pattern in policy.redaction.patterns:
        try:
            masked = re.sub(pattern, policy.redaction.mask, masked)
        except re.error:
            continue
    return masked


def validate_tool_call(
    *,
    policy: PolicySpec,
    agent_allowlist: list[str],
    tool_name: str,
) -> GuardDecision:
    """Validate tool call against allow/deny policies."""
    denylist = policy.tool_denylist or []
    if denylist and is_tool_allowed(tool_name, denylist):
        return GuardDecision(False, f"Tool '{tool_name}' denied by policy denylist", "tool_denied")

    allowlist = policy.tool_allowlist or agent_allowlist
    if allowlist and not is_tool_allowed(tool_name, allowlist):
        return GuardDecision(False, f"Tool '{tool_name}' not allowed", "tool_not_allowlisted")
    return GuardDecision(True)


def validate_handoff(
    *,
    from_agent: str,
    to_agent: str,
    payload: dict[str, Any],
) -> GuardDecision:
    """Basic handoff guard validation."""
    if from_agent == to_agent:
        return GuardDecision(False, "Self handoff blocked", "self_handoff")
    if not isinstance(payload, dict):
        return GuardDecision(False, "Handoff payload must be an object", "handoff_payload_invalid")
    return GuardDecision(True)


def maybe_abstain(
    *,
    policy: PolicySpec,
    confidence: float | None,
    has_citations: bool,
) -> AbstainResult | None:
    """Compute abstain decision from policy + confidence/citations."""
    if not policy.abstain.enabled:
        return None
    conf = confidence if confidence is not None else 1.0
    if conf < policy.abstain.confidence_threshold:
        return AbstainResult(reason=policy.abstain.reason_template, confidence=conf)
    if policy.abstain.require_citations_for_rag and not has_citations:
        return AbstainResult(reason="Missing required citations for RAG response", confidence=conf)
    return None
