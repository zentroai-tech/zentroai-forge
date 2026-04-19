"""IR v2 schema for multi-agent flows.

Defines the canonical multi-agent IR: multiple agents with isolated
graphs, handoff rules, budgets, and entrypoints.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# Re-use shared core graph types
from agent_compiler.models.ir import (
    Edge,
    Flow,
    LLMProvider,
    Node,
    FallbackSpec,
    RetrySpec,
    SchemaRef,
)


# ---------------------------------------------------------------------------
# New enums
# ---------------------------------------------------------------------------


class HandoffMode(str, Enum):
    """How control is transferred between agents."""

    CALL = "call"  # Shared context — child sees parent's node outputs
    DELEGATE = "delegate"  # Isolated context — child gets a fresh ExecutionContext


# ---------------------------------------------------------------------------
# Budget / LLM binding
# ---------------------------------------------------------------------------


class BudgetSpec(BaseModel):
    """Resource budgets for a single agent."""

    max_tokens: int | None = None
    max_tool_calls: int | None = None
    max_steps: int | None = None
    max_depth: int = Field(default=5, ge=1, le=20)


class AbstainSpec(BaseModel):
    """Abstain policy controls."""

    enabled: bool = True
    reason_template: str = "Insufficient confidence to continue safely."
    confidence_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    require_citations_for_rag: bool = False


class RedactionSpec(BaseModel):
    """Redaction policy for logs and artifacts."""

    enabled: bool = True
    patterns: list[str] = Field(default_factory=list)
    mask: str = "***REDACTED***"


class SanitizationSpec(BaseModel):
    """Input sanitization policy."""

    enabled: bool = True
    max_input_chars: int = Field(default=8000, ge=1, le=200000)
    strip_html: bool = True


class PolicySpec(BaseModel):
    """Policy controls (global and per-agent)."""

    tool_allowlist: list[str] = Field(default_factory=list)
    tool_denylist: list[str] = Field(default_factory=list)
    max_tool_calls: int | None = Field(default=None, ge=1)
    max_steps: int | None = Field(default=None, ge=1)
    max_depth: int | None = Field(default=None, ge=1, le=20)
    abstain: AbstainSpec = Field(default_factory=AbstainSpec)
    redaction: RedactionSpec = Field(default_factory=RedactionSpec)
    input_sanitization: SanitizationSpec = Field(default_factory=SanitizationSpec)
    allow_schema_soft_fail: bool = False


class LlmBinding(BaseModel):
    """Default LLM configuration for an agent."""

    provider: LLMProvider = LLMProvider.AUTO
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    system_prompt: str | None = None


# ---------------------------------------------------------------------------
# Graph spec (inner DAG per agent)
# ---------------------------------------------------------------------------


class GraphSpec(BaseModel):
    """A sub-graph owned by a single agent."""

    nodes: list[Node] = Field(..., min_length=1)
    edges: list[Edge] = Field(default_factory=list)
    root: str = Field(..., description="ID of the start node for this graph")

    @model_validator(mode="after")
    def validate_graph(self) -> "GraphSpec":
        """Validate DAG, node refs, and root existence."""
        node_ids = {node.id for node in self.nodes}

        # Root must exist
        if self.root not in node_ids:
            raise ValueError(
                f"Graph root '{self.root}' references unknown node. "
                f"Available: {sorted(node_ids)}"
            )

        # Edge references
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"Edge source '{edge.source}' references unknown node")
            if edge.target not in node_ids:
                raise ValueError(f"Edge target '{edge.target}' references unknown node")

        # DAG validation (Kahn's algorithm)
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        for edge in self.edges:
            adjacency[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(node_ids):
            raise ValueError("Agent graph contains a cycle — only DAGs are supported")

        return self


# ---------------------------------------------------------------------------
# Agent spec
# ---------------------------------------------------------------------------


class AgentSpec(BaseModel):
    """Definition of a single agent within a multi-agent flow."""

    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    graph: GraphSpec
    llm: LlmBinding = Field(default_factory=LlmBinding)
    tools_allowlist: list[str] = Field(default_factory=list)
    memory_namespace: str | None = None
    budgets: BudgetSpec = Field(default_factory=BudgetSpec)
    policies: PolicySpec | None = None
    retries: RetrySpec | None = None
    fallbacks: FallbackSpec | None = None


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


class HandoffGuard(BaseModel):
    """Optional guard condition on a handoff rule."""

    condition_template: str = ""
    fallback_agent_id: str | None = None


class HandoffRule(BaseModel):
    """A directed handoff between two agents."""

    from_agent_id: str
    to_agent_id: str
    mode: HandoffMode = HandoffMode.CALL
    guard: HandoffGuard | None = None
    input_schema: SchemaRef | None = None
    output_schema: SchemaRef | None = None

    @field_validator("input_schema", "output_schema", mode="before")
    @classmethod
    def coerce_empty_schema_ref(cls, value: Any) -> Any:
        """Treat empty schema placeholders as null refs."""
        if value is None:
            return None
        if isinstance(value, dict) and len(value) == 0:
            return None
        if isinstance(value, dict) and not value.get("ref"):
            return None
        return value


# ---------------------------------------------------------------------------
# Entrypoint / resources
# ---------------------------------------------------------------------------


class EntrypointSpec(BaseModel):
    """Named entrypoint into the multi-agent system."""

    name: str = "main"
    agent_id: str
    description: str = ""


class ResourceRegistry(BaseModel):
    """Shared resources accessible across agents."""

    shared_memory_namespaces: list[str] = Field(default_factory=list)
    global_tools: list[str] = Field(default_factory=list)
    # Named JSON Schemas managed from FE (schema://<id> refs).
    schema_contracts: dict[str, dict[str, Any]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# FlowIR v2 (top-level)
# ---------------------------------------------------------------------------


class FlowIRv2(BaseModel):
    """Complete multi-agent flow Intermediate Representation (v2)."""

    ir_version: Literal["2"] = "2"
    flow: Flow
    agents: list[AgentSpec] = Field(..., min_length=1)
    entrypoints: list[EntrypointSpec] = Field(..., min_length=1)
    handoffs: list[HandoffRule] = Field(default_factory=list)
    resources: ResourceRegistry = Field(default_factory=ResourceRegistry)
    policies: PolicySpec = Field(default_factory=PolicySpec)

    @model_validator(mode="after")
    def validate_multi_agent_structure(self) -> "FlowIRv2":
        """Validate cross-agent references."""
        agent_ids = {agent.id for agent in self.agents}

        # Entrypoint agent refs
        for ep in self.entrypoints:
            if ep.agent_id not in agent_ids:
                raise ValueError(
                    f"Entrypoint '{ep.name}' references unknown agent '{ep.agent_id}'. "
                    f"Available: {sorted(agent_ids)}"
                )

        # Handoff agent refs + no self-handoffs
        for handoff in self.handoffs:
            if handoff.from_agent_id not in agent_ids:
                raise ValueError(
                    f"Handoff from_agent_id '{handoff.from_agent_id}' references unknown agent"
                )
            if handoff.to_agent_id not in agent_ids:
                raise ValueError(
                    f"Handoff to_agent_id '{handoff.to_agent_id}' references unknown agent"
                )
            if handoff.from_agent_id == handoff.to_agent_id:
                raise ValueError(
                    f"Self-handoff not allowed: agent '{handoff.from_agent_id}' -> itself"
                )

            # Validate guard fallback ref
            if handoff.guard and handoff.guard.fallback_agent_id:
                if handoff.guard.fallback_agent_id not in agent_ids:
                    raise ValueError(
                        f"Handoff guard fallback_agent_id "
                        f"'{handoff.guard.fallback_agent_id}' references unknown agent"
                    )

        return self

    # ── Helpers ────────────────────────────────────────────────────

    def get_agent(self, agent_id: str) -> AgentSpec | None:
        """Get an agent by ID."""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None

    def get_entrypoint(self, name: str = "main") -> EntrypointSpec | None:
        """Get an entrypoint by name."""
        for ep in self.entrypoints:
            if ep.name == name:
                return ep
        return None

    def get_handoffs_from(self, agent_id: str) -> list[HandoffRule]:
        """Get all handoff rules originating from an agent."""
        return [h for h in self.handoffs if h.from_agent_id == agent_id]

    # ── Graph helper properties ──────────────────────────────────

    @property
    def nodes(self) -> list[Node]:
        """Flatten all agent nodes for graph helper consumers."""
        result: list[Node] = []
        for agent in self.agents:
            result.extend(agent.graph.nodes)
        return result

    @property
    def edges(self) -> list[Edge]:
        """Flatten all agent edges for graph helper consumers."""
        result: list[Edge] = []
        for agent in self.agents:
            result.extend(agent.graph.edges)
        return result
