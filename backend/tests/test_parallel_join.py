"""Tests for Parallel/Join node support."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.ir import Edge, Flow, Node, NodeType
from agent_compiler.models.ir_v2 import AgentSpec, EntrypointSpec, FlowIRv2, GraphSpec
from agent_compiler.runtime.executor import FlowExecutor
from agent_compiler.runtime.graph_runtime import AgentGraphRuntime


def _build_parallel_join_flow() -> FlowIRv2:
    return FlowIRv2(
        ir_version="2",
        flow=Flow(id="parallel_join_flow", name="Parallel Join Flow"),
        agents=[
            AgentSpec(
                id="main",
                name="Main",
                graph=GraphSpec(
                    root="fanout",
                    nodes=[
                        Node(
                            id="fanout",
                            type=NodeType.PARALLEL,
                            name="Fan-out",
                            params={"mode": "broadcast"},
                        ),
                        Node(
                            id="branch_a",
                            type=NodeType.OUTPUT,
                            name="Branch A",
                            params={"output_template": "A:{input}", "format": "text"},
                        ),
                        Node(
                            id="branch_b",
                            type=NodeType.OUTPUT,
                            name="Branch B",
                            params={"output_template": "B:{input}", "format": "text"},
                        ),
                        Node(
                            id="join",
                            type=NodeType.JOIN,
                            name="Join",
                            params={"strategy": "dict"},
                        ),
                        Node(
                            id="final",
                            type=NodeType.OUTPUT,
                            name="Final",
                            params={"output_template": "{current}", "format": "text"},
                        ),
                    ],
                    edges=[
                        Edge(source="fanout", target="branch_a"),
                        Edge(source="fanout", target="branch_b"),
                        Edge(source="branch_a", target="join"),
                        Edge(source="branch_b", target="join"),
                        Edge(source="join", target="final"),
                    ],
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="main")],
        handoffs=[],
    )


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with session_factory() as test_session:
        yield test_session

    await engine.dispose()


def test_parallel_join_ir_validation() -> None:
    flow_ir = _build_parallel_join_flow()
    agent = flow_ir.get_agent("main")
    assert agent is not None
    runtime_graph = AgentGraphRuntime(flow_ir.flow, agent.graph.nodes, agent.graph.edges)
    order = runtime_graph.get_topological_order()
    assert order[0] == "fanout"
    assert order[-1] == "final"
    assert set(runtime_graph.get_predecessors("join")) == {"branch_a", "branch_b"}


@pytest.mark.asyncio
async def test_parallel_join_execution_merges_predecessors(session: AsyncSession) -> None:
    flow_ir = _build_parallel_join_flow()
    executor = FlowExecutor(session)

    run = await executor.execute(flow_ir, {"input": "hello"})
    output = json.loads(run.output_json or "{}")
    node_outputs = output.get("node_outputs", {})
    join_output = node_outputs.get("join", {})

    assert join_output.get("strategy") == "dict"
    assert set(join_output.get("joined_from", [])) == {"branch_a", "branch_b"}
    merged = join_output.get("output", {})
    assert "branch_a" in merged
    assert "branch_b" in merged
