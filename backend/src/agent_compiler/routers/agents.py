"""Multi-agent management API endpoints."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.models.ir import parse_ir
from agent_compiler.models.ir import SchemaRef, RetrySpec, FallbackSpec
from agent_compiler.models.ir_v2 import (
    AgentSpec,
    BudgetSpec,
    EntrypointSpec,
    FlowIRv2,
    GraphSpec,
    HandoffMode,
    HandoffRule,
    LlmBinding,
    PolicySpec,
)
from agent_compiler.services.flow_service import FlowService

router = APIRouter(tags=["agents"])


# ── Request / Response Models ────────────────────────────────────────


class AgentCreate(BaseModel):
    """Request body for creating an agent."""

    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    root: str | None = None
    llm: dict[str, Any] = Field(default_factory=dict)
    tools_allowlist: list[str] = Field(default_factory=list)
    memory_namespace: str | None = None
    budgets: dict[str, Any] = Field(default_factory=dict)
    policies: dict[str, Any] | None = None
    retries: dict[str, Any] | None = None
    fallbacks: dict[str, Any] | None = None


class AgentUpdate(BaseModel):
    """Request body for updating an agent."""

    name: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    root: str | None = None
    llm: dict[str, Any] | None = None
    tools_allowlist: list[str] | None = None
    memory_namespace: str | None = None
    budgets: dict[str, Any] | None = None
    policies: dict[str, Any] | None = None
    retries: dict[str, Any] | None = None
    fallbacks: dict[str, Any] | None = None


class HandoffCreate(BaseModel):
    """Request body for creating a handoff rule."""

    from_agent_id: str
    to_agent_id: str
    mode: str = "call"
    guard: dict[str, Any] | None = None
    input_schema: SchemaRef | None = None
    output_schema: SchemaRef | None = None


# ── Helpers ──────────────────────────────────────────────────────────


def _get_v2_ir(flow) -> FlowIRv2:
    """Parse the flow's IR and ensure it's v2."""
    try:
        ir = parse_ir(json.loads(flow.ir_json))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not isinstance(ir, FlowIRv2):
        raise HTTPException(
            status_code=400,
            detail="Flow is not a v2 (multi-agent) flow. Convert it first.",
        )
    return ir


async def _save_ir(session: AsyncSession, flow, ir: FlowIRv2) -> None:
    """Persist updated v2 IR back to the flow record."""
    from datetime import datetime, timezone

    flow.ir_json = ir.model_dump_json()
    flow.updated_at = datetime.now(timezone.utc)
    session.add(flow)
    await session.commit()
    await session.refresh(flow)


# ── Agent CRUD ───────────────────────────────────────────────────────


@router.post("/flows/{flow_id}/agents", status_code=201)
async def add_agent(
    flow_id: str,
    agent_data: AgentCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a new agent to a v2 flow."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    ir = _get_v2_ir(flow)

    # Check for duplicate agent ID
    if ir.get_agent(agent_data.id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{agent_data.id}' already exists",
        )

    # Build the agent spec
    from agent_compiler.models.ir import Node, Edge

    nodes = [Node.model_validate(n) for n in agent_data.nodes]
    edges = [Edge.model_validate(e) for e in agent_data.edges]
    root = agent_data.root or (nodes[0].id if nodes else "")

    agent = AgentSpec(
        id=agent_data.id,
        name=agent_data.name,
        graph=GraphSpec(nodes=nodes, edges=edges, root=root),
        llm=LlmBinding.model_validate(agent_data.llm),
        tools_allowlist=agent_data.tools_allowlist,
        memory_namespace=agent_data.memory_namespace,
        budgets=BudgetSpec.model_validate(agent_data.budgets),
        policies=PolicySpec.model_validate(agent_data.policies) if agent_data.policies else None,
        retries=RetrySpec.model_validate(agent_data.retries) if agent_data.retries else None,
        fallbacks=FallbackSpec.model_validate(agent_data.fallbacks) if agent_data.fallbacks else None,
    )

    ir.agents.append(agent)
    await _save_ir(session, flow, ir)

    return agent.model_dump()


@router.get("/flows/{flow_id}/agents")
async def list_agents(
    flow_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List all agents in a v2 flow."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    ir = _get_v2_ir(flow)
    return [a.model_dump() for a in ir.agents]


@router.put("/flows/{flow_id}/agents/{agent_id}")
async def update_agent(
    flow_id: str,
    agent_id: str,
    agent_data: AgentUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update an agent's configuration."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    ir = _get_v2_ir(flow)
    agent = ir.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # Apply partial updates
    if agent_data.name is not None:
        agent.name = agent_data.name
    if agent_data.nodes is not None:
        from agent_compiler.models.ir import Node, Edge

        nodes = [Node.model_validate(n) for n in agent_data.nodes]
        edges = [Edge.model_validate(e) for e in (agent_data.edges or [])]
        root = agent_data.root or (nodes[0].id if nodes else agent.graph.root)
        agent.graph = GraphSpec(nodes=nodes, edges=edges, root=root)
    if agent_data.llm is not None:
        agent.llm = LlmBinding.model_validate(agent_data.llm)
    if agent_data.tools_allowlist is not None:
        agent.tools_allowlist = agent_data.tools_allowlist
    if agent_data.memory_namespace is not None:
        agent.memory_namespace = agent_data.memory_namespace
    if agent_data.budgets is not None:
        agent.budgets = BudgetSpec.model_validate(agent_data.budgets)
    if agent_data.policies is not None:
        agent.policies = PolicySpec.model_validate(agent_data.policies)
    if agent_data.retries is not None:
        agent.retries = RetrySpec.model_validate(agent_data.retries)
    if agent_data.fallbacks is not None:
        agent.fallbacks = FallbackSpec.model_validate(agent_data.fallbacks)

    await _save_ir(session, flow, ir)
    return agent.model_dump()


@router.delete("/flows/{flow_id}/agents/{agent_id}", status_code=204)
async def delete_agent(
    flow_id: str,
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove an agent from a v2 flow."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    ir = _get_v2_ir(flow)

    # Can't delete if it's the last agent
    if len(ir.agents) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last agent in a flow",
        )

    # Remove agent
    ir.agents = [a for a in ir.agents if a.id != agent_id]

    # Remove associated handoffs
    ir.handoffs = [
        h for h in ir.handoffs
        if h.from_agent_id != agent_id and h.to_agent_id != agent_id
    ]

    # Remove associated entrypoints
    ir.entrypoints = [e for e in ir.entrypoints if e.agent_id != agent_id]

    # Ensure at least one entrypoint remains
    if not ir.entrypoints:
        ir.entrypoints = [
            EntrypointSpec(name="main", agent_id=ir.agents[0].id)
        ]

    await _save_ir(session, flow, ir)


# ── Handoff CRUD ─────────────────────────────────────────────────────


@router.post("/flows/{flow_id}/handoffs", status_code=201)
async def add_handoff(
    flow_id: str,
    handoff_data: HandoffCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a handoff rule to a v2 flow."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    ir = _get_v2_ir(flow)

    # Validate agent references
    if ir.get_agent(handoff_data.from_agent_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{handoff_data.from_agent_id}' not found",
        )
    if ir.get_agent(handoff_data.to_agent_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{handoff_data.to_agent_id}' not found",
        )
    if handoff_data.from_agent_id == handoff_data.to_agent_id:
        raise HTTPException(
            status_code=400,
            detail="Self-handoffs are not allowed",
        )

    handoff = HandoffRule(
        from_agent_id=handoff_data.from_agent_id,
        to_agent_id=handoff_data.to_agent_id,
        mode=HandoffMode(handoff_data.mode),
        input_schema=handoff_data.input_schema,
        output_schema=handoff_data.output_schema,
    )

    ir.handoffs.append(handoff)
    await _save_ir(session, flow, ir)

    return handoff.model_dump()


@router.get("/flows/{flow_id}/handoffs")
async def list_handoffs(
    flow_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List all handoff rules in a v2 flow."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    ir = _get_v2_ir(flow)
    return [h.model_dump() for h in ir.handoffs]


@router.delete("/flows/{flow_id}/handoffs/{index}", status_code=204)
async def delete_handoff(
    flow_id: str,
    index: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a handoff rule by index."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    ir = _get_v2_ir(flow)

    if index < 0 or index >= len(ir.handoffs):
        raise HTTPException(
            status_code=404,
            detail=f"Handoff index {index} out of range",
        )

    ir.handoffs.pop(index)
    await _save_ir(session, flow, ir)
