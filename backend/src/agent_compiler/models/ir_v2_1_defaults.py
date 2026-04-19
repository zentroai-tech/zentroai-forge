"""Helpers to normalize v2.1 policy/retry/fallback defaults."""

from __future__ import annotations

from agent_compiler.models.ir_v2 import AgentSpec, FlowIRv2, PolicySpec


def merge_policy(base: PolicySpec, override: PolicySpec | None) -> PolicySpec:
    """Merge policy override over global defaults."""
    if override is None:
        return base
    merged = base.model_copy(deep=True)
    data = override.model_dump(exclude_unset=True)
    if "abstain" in data:
        merged.abstain = merged.abstain.model_copy(update=data["abstain"])
        data.pop("abstain")
    if "redaction" in data:
        merged.redaction = merged.redaction.model_copy(update=data["redaction"])
        data.pop("redaction")
    if "input_sanitization" in data:
        merged.input_sanitization = merged.input_sanitization.model_copy(
            update=data["input_sanitization"]
        )
        data.pop("input_sanitization")
    return merged.model_copy(update=data)


def normalize_flow_v21_defaults(ir: FlowIRv2) -> FlowIRv2:
    """Ensure v2.1 defaults are hydrated for existing flows."""
    global_policy = ir.policies or PolicySpec()
    agents: list[AgentSpec] = []
    for agent in ir.agents:
        agent_copy = agent.model_copy(deep=True)
        agent_copy.policies = merge_policy(global_policy, agent_copy.policies)
        agents.append(agent_copy)
    return ir.model_copy(update={"policies": global_policy, "agents": agents})
