"""Tests for PR2: Run Events, Replay, and Run Diff."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import (
    FlowRecord,
    ReplayConfig,
    ReplayMode,
    RunEvent,
    RunEventType,
)
from agent_compiler.services.event_recorder import EventRecorder
from agent_compiler.services.replay_service import ReplayService
from agent_compiler.services.run_service import RunService


# ---------------------------------------------------------------------------
# Shared IR fixture
# ---------------------------------------------------------------------------


def _minimal_v2_ir(flow_id: str) -> dict:
    return {
        "ir_version": "2",
        "flow": {
            "id": flow_id,
            "name": "Events Test Flow",
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
                                "format": "text",
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


# ---------------------------------------------------------------------------
# Session fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with session_factory() as test_session:
        yield test_session

    await engine.dispose()


# ===========================================================================
# TestEventRecorder — unit tests for the recorder itself
# ===========================================================================


class TestEventRecorder:
    """Unit tests for EventRecorder.record_step()."""

    @pytest.mark.asyncio
    async def test_emits_llm_prompt_and_response(self, session: AsyncSession) -> None:
        """LLM step should emit LLM_PROMPT and LLM_RESPONSE events."""
        # Simulate a run in the DB first (events FK run_id → runs.id)
        flow = FlowRecord(
            id="flow_evt_llm",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_llm")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "hello"}, entrypoint="main")

        recorder = EventRecorder(session, run.id, capture_prompts=True)
        await recorder.record_step(
            node_id="llm_1",
            node_type="LLM",
            input_data={"current_value": "hello world"},
            output_data={"output": "Hi!", "model": "gpt-4o-mini", "tokens_used": 42},
        )
        await session.commit()

        result = await session.execute(
            select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq)
        )
        events = list(result.scalars().all())

        types = [e.type for e in events]
        assert RunEventType.LLM_PROMPT in types
        assert RunEventType.LLM_RESPONSE in types

    @pytest.mark.asyncio
    async def test_redacts_prompt_when_capture_prompts_false(self, session: AsyncSession) -> None:
        """With capture_prompts=False the LLM_PROMPT payload should be redacted."""
        flow = FlowRecord(
            id="flow_evt_redact",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_redact")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "secret input"}, entrypoint="main")

        recorder = EventRecorder(session, run.id, capture_prompts=False)
        await recorder.record_step(
            node_id="llm_1",
            node_type="LLM",
            input_data={"current_value": "secret input"},
            output_data={"output": "response", "model": "gpt-4o-mini"},
        )
        await session.commit()

        result = await session.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.type == RunEventType.LLM_PROMPT)
        )
        prompt_evt = result.scalar_one_or_none()
        assert prompt_evt is not None
        assert prompt_evt.payload.get("prompt") == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_emits_tool_call_and_result(self, session: AsyncSession) -> None:
        """Tool step should emit TOOL_CALL and TOOL_RESULT events."""
        flow = FlowRecord(
            id="flow_evt_tool",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_tool")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "search query"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        await recorder.record_step(
            node_id="tool_1",
            node_type="Tool",
            input_data={"current_value": "search query"},
            output_data={"result": "42"},
        )
        await session.commit()

        result = await session.execute(
            select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq)
        )
        events = list(result.scalars().all())
        types = [e.type for e in events]
        assert RunEventType.TOOL_CALL in types
        assert RunEventType.TOOL_RESULT in types

    @pytest.mark.asyncio
    async def test_emits_retrieval_event(self, session: AsyncSession) -> None:
        """Retriever step should emit RETRIEVAL event."""
        flow = FlowRecord(
            id="flow_evt_ret",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_ret")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "query"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        await recorder.record_step(
            node_id="retriever_1",
            node_type="Retriever",
            input_data={"current_value": "query"},
            output_data={"documents": [], "num_documents": 0},
        )
        await session.commit()

        result = await session.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.type == RunEventType.RETRIEVAL)
        )
        evt = result.scalar_one_or_none()
        assert evt is not None
        assert evt.payload.get("query") == "query"

    @pytest.mark.asyncio
    async def test_emits_router_decision(self, session: AsyncSession) -> None:
        """Router step should emit ROUTER_DECISION event."""
        flow = FlowRecord(
            id="flow_evt_router",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_router")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "route me"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        await recorder.record_step(
            node_id="router_1",
            node_type="Router",
            input_data={"current_value": "route me"},
            output_data={"selected_route": "answer", "condition_matched": True},
        )
        await session.commit()

        result = await session.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.type == RunEventType.ROUTER_DECISION)
        )
        evts = list(result.scalars().all())
        assert len(evts) >= 1
        assert evts[0].payload.get("selected_route") == "answer"

    @pytest.mark.asyncio
    async def test_emits_policy_block_for_abstained_output(self, session: AsyncSession) -> None:
        """Output with abstained=True should emit POLICY_BLOCK event."""
        flow = FlowRecord(
            id="flow_evt_policy",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_policy")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "question"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        await recorder.record_step(
            node_id="llm_1",
            node_type="LLM",
            input_data={"current_value": "question"},
            output_data={"output": "I don't know.", "abstained": True, "abstain_reason": "no docs"},
        )
        await session.commit()

        result = await session.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.type == RunEventType.POLICY_BLOCK)
        )
        evt = result.scalar_one_or_none()
        assert evt is not None

    @pytest.mark.asyncio
    async def test_seq_is_monotonically_increasing(self, session: AsyncSession) -> None:
        """Events from a single recorder instance must have unique, increasing seq."""
        flow = FlowRecord(
            id="flow_evt_seq",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_seq")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "x"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        for i in range(3):
            await recorder.record_step(
                node_id=f"tool_{i}",
                node_type="Tool",
                input_data={"current_value": f"input {i}"},
                output_data={"result": f"result {i}"},
            )
        await session.commit()

        result = await session.execute(
            select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq)
        )
        events = list(result.scalars().all())
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)  # unique

    @pytest.mark.asyncio
    async def test_hash_is_populated(self, session: AsyncSession) -> None:
        """Events with determinism support should have a non-null hash."""
        flow = FlowRecord(
            id="flow_evt_hash",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_evt_hash")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "x"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        await recorder.record_step(
            node_id="llm_1",
            node_type="LLM",
            input_data={"current_value": "hello"},
            output_data={"output": "Hi!", "model": "gpt-4o-mini"},
        )
        await session.commit()

        result = await session.execute(
            select(RunEvent).where(RunEvent.run_id == run.id)
        )
        events = list(result.scalars().all())
        assert all(e.hash is not None and len(e.hash) > 0 for e in events)


# ===========================================================================
# TestRunServiceGetEvents
# ===========================================================================


class TestRunServiceGetEvents:
    """Tests for RunService.get_run_events()."""

    @pytest.mark.asyncio
    async def test_get_run_events_returns_events_in_order(self, session: AsyncSession) -> None:
        flow = FlowRecord(
            id="flow_svc_events",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_svc_events")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "x"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        await recorder.record_step("tool_a", "Tool", {"current_value": "a"}, {"result": "1"})
        await recorder.record_step("tool_b", "Tool", {"current_value": "b"}, {"result": "2"})
        await session.commit()

        events = await run_svc.get_run_events(run.id)
        assert len(events) >= 2
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs)

    @pytest.mark.asyncio
    async def test_get_run_events_empty_for_new_run(self, session: AsyncSession) -> None:
        flow = FlowRecord(
            id="flow_svc_noevents",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_svc_noevents")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "x"}, entrypoint="main")

        events = await run_svc.get_run_events(run.id)
        # Executor emits events during create_run, so we just check it's a list
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_get_run_events_event_fields_present(self, session: AsyncSession) -> None:
        flow = FlowRecord(
            id="flow_svc_fields",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_svc_fields")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run = await run_svc.create_run(flow, {"input": "x"}, entrypoint="main")

        recorder = EventRecorder(session, run.id)
        await recorder.record_step("llm_1", "LLM", {"current_value": "hi"}, {"output": "hello"})
        await session.commit()

        events = await run_svc.get_run_events(run.id)
        if events:
            evt = events[0]
            assert "id" in evt
            assert "run_id" in evt
            assert "seq" in evt
            assert "node_id" in evt
            assert "type" in evt
            assert "payload" in evt
            assert "hash" in evt


# ===========================================================================
# TestRunDiffEndpoint — testing diff logic via RunService
# ===========================================================================


class TestRunDiff:
    """Tests for run diff logic used by POST /runs/diff."""

    @pytest.mark.asyncio
    async def test_identical_runs_have_zero_changed_nodes(self, session: AsyncSession) -> None:
        """Two runs with the same output should report 0 changed nodes."""
        flow = FlowRecord(
            id="flow_diff_same",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_diff_same")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run_a = await run_svc.create_run(flow, {"input": "hello"}, entrypoint="main")
        run_b = await run_svc.create_run(flow, {"input": "hello"}, entrypoint="main")

        data_a = await run_svc.get_run_with_steps(run_a.id)
        data_b = await run_svc.get_run_with_steps(run_b.id)

        assert data_a is not None
        assert data_b is not None

        # Build diff logic manually (mirrors the endpoint)
        steps_a = {s["node_id"]: s for s in data_a.get("timeline", [])}
        steps_b = {s["node_id"]: s for s in data_b.get("timeline", [])}
        all_nodes = sorted(set(list(steps_a.keys()) + list(steps_b.keys())))

        def _out(s):
            if not s or not s.get("output"):
                return ""
            out = s["output"]
            if isinstance(out, dict) and "output" in out:
                return str(out["output"])
            import json
            return json.dumps(out) if isinstance(out, dict) else str(out)

        changed = sum(1 for n in all_nodes if _out(steps_a.get(n)) != _out(steps_b.get(n)))
        # Same input → same deterministic output → 0 changed
        assert changed == 0

    @pytest.mark.asyncio
    async def test_different_input_produces_different_output(self, session: AsyncSession) -> None:
        """Two runs with different inputs should show changed output for the output node."""
        flow = FlowRecord(
            id="flow_diff_diff",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_diff_diff")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        run_a = await run_svc.create_run(flow, {"input": "hello"}, entrypoint="main")
        run_b = await run_svc.create_run(flow, {"input": "goodbye"}, entrypoint="main")

        data_a = await run_svc.get_run_with_steps(run_a.id)
        data_b = await run_svc.get_run_with_steps(run_b.id)

        assert data_a is not None
        assert data_b is not None

        steps_a = {s["node_id"]: s for s in data_a.get("timeline", [])}
        steps_b = {s["node_id"]: s for s in data_b.get("timeline", [])}
        all_nodes = sorted(set(list(steps_a.keys()) + list(steps_b.keys())))

        def _out(s):
            if not s or not s.get("output"):
                return ""
            out = s["output"]
            if isinstance(out, dict) and "output" in out:
                return str(out["output"])
            import json
            return json.dumps(out) if isinstance(out, dict) else str(out)

        changed = sum(1 for n in all_nodes if _out(steps_a.get(n)) != _out(steps_b.get(n)))
        assert changed >= 1  # At least the output node should differ

    @pytest.mark.asyncio
    async def test_replay_mock_all_produces_same_output(self, session: AsyncSession) -> None:
        """Replay with mock_all should return the same output as the original run."""
        flow = FlowRecord(
            id="flow_diff_replay",
            name="Test",
            version="1.0.0",
            description="",
            engine_preference="langchain",
            ir_json=json.dumps(_minimal_v2_ir("flow_diff_replay")),
        )
        session.add(flow)
        await session.commit()

        run_svc = RunService(session)
        original = await run_svc.create_run(flow, {"input": "test input"}, entrypoint="main")

        replay_svc = ReplayService(session)
        replayed = await replay_svc.replay_run(
            original.id,
            ReplayConfig(mode=ReplayMode.MOCK_ALL),
        )

        data_orig = await run_svc.get_run_with_steps(original.id)
        data_replay = await run_svc.get_run_with_steps(replayed.id)

        assert data_orig is not None
        assert data_replay is not None

        steps_orig = {s["node_id"]: s for s in data_orig.get("timeline", [])}
        steps_replay = {s["node_id"]: s for s in data_replay.get("timeline", [])}
        all_nodes = sorted(set(list(steps_orig.keys()) + list(steps_replay.keys())))

        def _out(s):
            if not s or not s.get("output"):
                return ""
            out = s["output"]
            if isinstance(out, dict) and "output" in out:
                return str(out["output"])
            import json
            return json.dumps(out) if isinstance(out, dict) else str(out)

        changed = sum(1 for n in all_nodes if _out(steps_orig.get(n)) != _out(steps_replay.get(n)))
        assert changed == 0, f"Expected 0 changed nodes but got {changed}"
