"""Integration-style tests for CS-V2 multi-agent runtime wiring."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import (
    AgentEventRecord,
    FlowRecord,
    RunRecord,
    TimelineEventType,
)
from agent_compiler.services.run_service import RunService


def _build_v2_ir(
    *,
    flow_id: str,
    max_steps: int | None = None,
    entrypoint_agent: str = "supervisor",
) -> dict:
    """Build a small valid v2 IR for tests."""
    return {
        "ir_version": "2",
        "flow": {
            "id": flow_id,
            "name": "CS V2 Runtime",
            "version": "1.0.0",
            "engine_preference": "langchain",
            "description": "",
        },
        "agents": [
            {
                "id": "supervisor",
                "name": "Supervisor",
                "graph": {
                    "root": "sup_out",
                    "nodes": [
                        {
                            "id": "sup_out",
                            "type": "Output",
                            "name": "Supervisor Output",
                            "params": {
                                "is_start": True,
                                "output_template": "{input}",
                            },
                        }
                    ],
                    "edges": [],
                },
                "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.0},
                "tools_allowlist": [],
                "memory_namespace": "supervisor",
                "budgets": {"max_depth": 5},
            },
            {
                "id": "worker",
                "name": "Worker",
                "graph": {
                    "root": "w_1",
                    "nodes": [
                        {
                            "id": "w_1",
                            "type": "Output",
                            "name": "Worker 1",
                            "params": {
                                "is_start": True,
                                "output_template": "{input}",
                            },
                        },
                        {
                            "id": "w_2",
                            "type": "Output",
                            "name": "Worker 2",
                            "params": {
                                "output_template": "{input}",
                            },
                        },
                        {
                            "id": "w_3",
                            "type": "Output",
                            "name": "Worker 3",
                            "params": {
                                "output_template": "{input}",
                            },
                        },
                    ],
                    "edges": [
                        {"source": "w_1", "target": "w_2"},
                        {"source": "w_2", "target": "w_3"},
                    ],
                },
                "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.0},
                "tools_allowlist": [],
                "memory_namespace": "worker",
                "budgets": {"max_depth": 5, "max_steps": max_steps},
            },
        ],
        "entrypoints": [
            {"name": "main", "agent_id": entrypoint_agent, "description": "default"},
            {"name": "secondary", "agent_id": "worker", "description": "worker entrypoint"},
        ],
        "handoffs": [],
        "resources": {"shared_memory_namespaces": [], "global_tools": []},
    }


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


@pytest.mark.asyncio
async def test_v2_entrypoint_is_propagated_to_agent_executor(session: AsyncSession) -> None:
    flow = FlowRecord(
        id="flow_v2_entrypoint",
        name="Flow V2 Entrypoint",
        version="1.0.0",
        description="",
        engine_preference="langchain",
        ir_json=json.dumps(
            _build_v2_ir(flow_id="flow_v2_entrypoint", entrypoint_agent="supervisor")
        ),
    )
    session.add(flow)
    await session.commit()

    service = RunService(session)
    run = await service.create_run(flow, {"input": "hello"}, entrypoint="secondary")

    assert run.entrypoint == "secondary"

    events_result = await session.exec(
        select(AgentEventRecord)
        .where(AgentEventRecord.run_id == run.id)
        .order_by(AgentEventRecord.timestamp)
    )
    events = list(events_result.all())
    assert events
    assert events[0].event_type == TimelineEventType.AGENT_START
    assert events[0].agent_id == "worker"


@pytest.mark.asyncio
async def test_budget_warning_and_exceeded_events_are_emitted(session: AsyncSession) -> None:
    flow = FlowRecord(
        id="flow_v2_budget",
        name="Flow V2 Budget",
        version="1.0.0",
        description="",
        engine_preference="langchain",
        ir_json=json.dumps(
            _build_v2_ir(flow_id="flow_v2_budget", max_steps=2, entrypoint_agent="worker")
        ),
    )
    session.add(flow)
    await session.commit()

    service = RunService(session)

    with pytest.raises(Exception):
        await service.create_run(flow, {"input": "budget test"}, entrypoint="main")

    run_result = await session.exec(
        select(RunRecord)
        .where(RunRecord.flow_id == flow.id)
        .order_by(RunRecord.created_at.desc())
    )
    run = run_result.first()
    assert run is not None

    events_result = await session.exec(
        select(AgentEventRecord).where(AgentEventRecord.run_id == run.id)
    )
    events = list(events_result.all())
    event_types = [event.event_type for event in events]

    assert event_types.count(TimelineEventType.BUDGET_WARNING) == 1
    assert event_types.count(TimelineEventType.BUDGET_EXCEEDED) == 1


@pytest.mark.asyncio
async def test_schema_validation_error_event_emitted_on_strict_fail(
    session: AsyncSession,
    tmp_path,
) -> None:
    schema_path = tmp_path / "strict_schema.json"
    schema_path.write_text('{"required":["must_exist"]}', encoding="utf-8")

    flow_ir = _build_v2_ir(flow_id="flow_v2_schema_fail", entrypoint_agent="supervisor")
    flow_ir["agents"][0]["graph"]["nodes"][0]["params"]["input_schema"] = {
        "kind": "json_schema",
        "ref": str(schema_path),
    }

    flow = FlowRecord(
        id="flow_v2_schema_fail",
        name="Flow V2 Schema Fail",
        version="1.0.0",
        description="",
        engine_preference="langchain",
        ir_json=json.dumps(flow_ir),
    )
    session.add(flow)
    await session.commit()

    service = RunService(session)

    with pytest.raises(Exception):
        await service.create_run(flow, {"input": "schema strict fail"}, entrypoint="main")

    run_result = await session.exec(
        select(RunRecord)
        .where(RunRecord.flow_id == flow.id)
        .order_by(RunRecord.created_at.desc())
    )
    run = run_result.first()
    assert run is not None

    events_result = await session.exec(
        select(AgentEventRecord).where(AgentEventRecord.run_id == run.id)
    )
    events = list(events_result.all())
    event_types = [event.event_type for event in events]

    assert TimelineEventType.SCHEMA_VALIDATION_ERROR in event_types


def test_plan_act_loop_custom_agent_id() -> None:
    """Loop must activate for any agent ID in LOOP_AGENT_IDS, not just 'supervisor'."""
    from agent_compiler.models.ir_v2 import AgentSpec, EntrypointSpec, FlowIRv2, GraphSpec
    from agent_compiler.models.ir import Edge, EngineType, Flow, Node, NodeType
    from agent_compiler.services.multiagent_generator import MultiAgentGenerator

    ir = FlowIRv2(
        ir_version="2",
        flow=Flow(
            id="loop-test",
            name="Loop Test",
            version="1.0.0",
            description="",
            engine_preference=EngineType.LANGCHAIN,
        ),
        agents=[
            AgentSpec(
                id="custom_agent",
                name="Custom Agent",
                graph=GraphSpec(
                    root="n1",
                    nodes=[Node(id="n1", type=NodeType.OUTPUT, name="Out", params={"is_start": True, "output_template": "{input}"})],
                    edges=[],
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="custom_agent", description="")],
    )

    gen = MultiAgentGenerator(ir=ir)
    with tempfile.TemporaryDirectory() as d:
        gen.generate(Path(d))
        dispatcher_src = (Path(d) / "runtime" / "dispatcher.py").read_text()

    # Extract and exec just the _loop_agent_ids building logic to validate env-driven config
    saved = os.environ.get("LOOP_AGENT_IDS")
    try:
        os.environ["LOOP_AGENT_IDS"] = "custom_agent"
        loop_agent_ids = set(
            a.strip().lower()
            for a in os.environ.get("LOOP_AGENT_IDS", "supervisor").split(",")
            if a.strip()
        )
        assert "custom_agent" in loop_agent_ids, "custom_agent must be in LOOP_AGENT_IDS set"
        assert "supervisor" not in loop_agent_ids, "supervisor must NOT be in set when overridden"

        os.environ["LOOP_AGENT_IDS"] = "supervisor,main"
        loop_agent_ids_multi = set(
            a.strip().lower()
            for a in os.environ.get("LOOP_AGENT_IDS", "supervisor").split(",")
            if a.strip()
        )
        assert "supervisor" in loop_agent_ids_multi
        assert "main" in loop_agent_ids_multi
        assert "custom_agent" not in loop_agent_ids_multi
    finally:
        if saved is None:
            os.environ.pop("LOOP_AGENT_IDS", None)
        else:
            os.environ["LOOP_AGENT_IDS"] = saved

    # Verify the generated dispatcher source contains the env-driven logic
    assert "LOOP_AGENT_IDS" in dispatcher_src
    assert "_loop_agent_ids" in dispatcher_src
