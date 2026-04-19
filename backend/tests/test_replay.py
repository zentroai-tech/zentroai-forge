"""Replay regression tests for v2 flows."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import FlowRecord, ReplayConfig, ReplayMode
from agent_compiler.services.replay_service import ReplayService
from agent_compiler.services.run_service import RunService


def _build_replay_ir(flow_id: str) -> dict:
    return {
        "ir_version": "2",
        "flow": {
            "id": flow_id,
            "name": "Replay Flow",
            "version": "1.0.0",
            "engine_preference": "langchain",
            "description": "",
        },
        "agents": [
            {
                "id": "main",
                "name": "Main",
                "graph": {
                    "root": "out_1",
                    "nodes": [
                        {
                            "id": "out_1",
                            "type": "Output",
                            "name": "Output",
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
                "memory_namespace": "main",
                "budgets": {"max_depth": 5},
            }
        ],
        "entrypoints": [{"name": "main", "agent_id": "main", "description": "default"}],
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
async def test_replay_exact_creates_new_run_with_metadata(session: AsyncSession) -> None:
    flow = FlowRecord(
        id="flow_replay_exact",
        name="Replay Exact",
        version="1.0.0",
        description="",
        engine_preference="langchain",
        ir_json=json.dumps(_build_replay_ir("flow_replay_exact")),
    )
    session.add(flow)
    await session.commit()

    run_service = RunService(session)
    original = await run_service.create_run(flow, {"input": "hello replay"}, entrypoint="main")

    replay_service = ReplayService(session)
    replay = await replay_service.replay_run(original.id)

    assert replay.id != original.id
    assert replay.flow_id == original.flow_id
    assert replay.status.value == "completed"
    assert replay.output_data == original.output_data
    assert replay.meta.get("replay_of") == original.id
    assert replay.meta.get("replay_mode") == ReplayMode.EXACT.value


@pytest.mark.asyncio
async def test_replay_mock_all_records_mocked_nodes(session: AsyncSession) -> None:
    flow = FlowRecord(
        id="flow_replay_mock_all",
        name="Replay Mock All",
        version="1.0.0",
        description="",
        engine_preference="langchain",
        ir_json=json.dumps(_build_replay_ir("flow_replay_mock_all")),
    )
    session.add(flow)
    await session.commit()

    run_service = RunService(session)
    original = await run_service.create_run(flow, {"input": "hello replay"}, entrypoint="main")

    replay_service = ReplayService(session)
    replay = await replay_service.replay_run(
        original.id,
        ReplayConfig(mode=ReplayMode.MOCK_ALL),
    )

    assert replay.id != original.id
    assert replay.meta.get("replay_of") == original.id
    assert replay.meta.get("replay_mode") == ReplayMode.MOCK_ALL.value
    assert isinstance(replay.meta.get("mocked_nodes"), list)
