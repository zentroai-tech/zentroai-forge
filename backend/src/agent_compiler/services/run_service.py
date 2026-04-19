"""Run management service."""

import json
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import AgentEventRecord, FlowRecord, RunEvent, RunRecord, StepRecord
from agent_compiler.models.ir import parse_ir
from agent_compiler.observability.logging import get_logger
from agent_compiler.runtime.agent_executor import AgentExecutor
from agent_compiler.runtime.executor import FlowExecutor

logger = get_logger(__name__)


class RunService:
    """Service for managing flow runs."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.executor = FlowExecutor(session)

    async def create_run(
        self,
        flow: FlowRecord,
        input_data: dict[str, Any],
        entrypoint: str | None = None,
    ) -> RunRecord:
        """Create and execute a new run.

        Args:
            flow: The flow to run
            input_data: Input data for the run

        Returns:
            The completed run record
        """
        # Parse flow IR (v2-only)
        flow_ir = parse_ir(json.loads(flow.ir_json))

        agent_executor = AgentExecutor(self.session)
        run = await agent_executor.execute(
            ir=flow_ir,
            input_data=input_data,
            entrypoint=entrypoint or "main",
        )

        logger.info(f"Completed run: {run.id} with status: {run.status}")
        return run

    async def get_run(self, run_id: str) -> RunRecord | None:
        """Get a run by ID."""
        statement = select(RunRecord).where(RunRecord.id == run_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        flow_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RunRecord]:
        """List runs for a flow with pagination."""
        statement = (
            select(RunRecord)
            .where(RunRecord.flow_id == flow_id)
            .order_by(RunRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_run_steps(self, run_id: str) -> list[StepRecord]:
        """Get all steps for a run in execution order."""
        statement = (
            select(StepRecord)
            .where(StepRecord.run_id == run_id)
            .order_by(StepRecord.step_order)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def delete_run(self, run_id: str) -> bool:
        """Delete a run and its associated steps.

        Args:
            run_id: The run ID to delete

        Returns:
            True if deleted, False if not found
        """
        run = await self.get_run(run_id)
        if run is None:
            return False

        # Steps are cascade-deleted via relationship config
        await self.session.delete(run)
        await self.session.commit()
        logger.info(f"Deleted run: {run_id}")
        return True

    async def delete_all_runs(self, flow_id: str) -> int:
        """Delete all runs for a flow.

        Args:
            flow_id: The flow ID

        Returns:
            Number of runs deleted
        """
        runs = await self.list_runs(flow_id, limit=10000)
        count = len(runs)
        for run in runs:
            await self.session.delete(run)
        await self.session.commit()
        logger.info(f"Deleted {count} runs for flow: {flow_id}")
        return count

    async def replay_run(self, run_id: str) -> RunRecord:
        """Replay a run using its stored IR snapshot.

        Args:
            run_id: The run ID to replay

        Returns:
            A new run record with the replay results
        """
        return await self.executor.replay_run(run_id)

    async def get_run_with_steps(self, run_id: str) -> dict[str, Any] | None:
        """Get a run with its steps formatted for API response."""
        run = await self.get_run(run_id)
        if run is None:
            return None

        steps = await self.get_run_steps(run_id)

        # Calculate total run duration
        run_duration_ms = None
        if run.started_at and run.finished_at:
            run_duration_ms = (run.finished_at - run.started_at).total_seconds() * 1000

        # Include agent events if any exist
        agent_events = await self.get_agent_timeline(run_id)

        result = {
            "id": run.id,
            "flow_id": run.flow_id,
            "status": run.status.value,
            "entrypoint": getattr(run, "entrypoint", "main"),
            "input": json.loads(run.input_json) if run.input_json else {},
            "output": json.loads(run.output_json) if run.output_json else None,
            "error_message": run.error_message,
            "meta": json.loads(run.meta_json) if run.meta_json else {},
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "created_at": run.created_at.isoformat(),
            "duration_ms": run_duration_ms,
            "timeline": [
                self._format_step(step)
                for step in steps
            ],
        }

        if agent_events:
            result["agent_events"] = agent_events

        return result

    def _format_step(self, step: StepRecord) -> dict[str, Any]:
        """Format a step record for API response."""
        # Calculate step duration
        duration_ms = None
        if step.started_at and step.finished_at:
            duration_ms = (step.finished_at - step.started_at).total_seconds() * 1000

        # Parse output to extract key fields for display
        output = json.loads(step.output_json) if step.output_json else None
        meta = json.loads(step.meta_json) if step.meta_json else {}

        # Token info
        tokens = None
        if hasattr(step, "tokens_total") and step.tokens_total is not None:
            tokens = {
                "input": getattr(step, "tokens_input", None),
                "output": getattr(step, "tokens_output", None),
                "total": step.tokens_total,
            }

        result = {
            "step_id": step.id,
            "node_id": step.node_id,
            "node_type": step.node_type,
            "status": step.status.value,
            "order": step.step_order,
            "input": json.loads(step.input_json) if step.input_json else {},
            "output": output,
            "meta": meta,
            "error_message": step.error_message,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "finished_at": step.finished_at.isoformat() if step.finished_at else None,
            "duration_ms": duration_ms,
            "model_name": getattr(step, "model_name", None),
            "tokens": tokens,
        }

        # Multi-agent fields
        agent_id = getattr(step, "agent_id", None)
        if agent_id:
            result["agent_id"] = agent_id
            result["depth"] = getattr(step, "depth", 0)
            result["parent_step_id"] = getattr(step, "parent_step_id", None)

        return result

    async def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        """Get fine-grained debug timeline events for a run.

        Args:
            run_id: The run ID

        Returns:
            List of RunEvent dicts ordered by seq
        """
        statement = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq)
        )
        result = await self.session.execute(statement)
        events = list(result.scalars().all())

        return [
            {
                "id": evt.id,
                "run_id": evt.run_id,
                "ts": evt.ts.isoformat() if evt.ts else None,
                "seq": evt.seq,
                "node_id": evt.node_id,
                "type": evt.type.value,
                "payload": evt.payload,
                "hash": evt.hash,
            }
            for evt in events
        ]

    async def get_agent_timeline(self, run_id: str) -> list[dict[str, Any]]:
        """Get agent-level timeline events for a run.

        Args:
            run_id: The run ID

        Returns:
            List of agent events, ordered by timestamp
        """
        statement = (
            select(AgentEventRecord)
            .where(AgentEventRecord.run_id == run_id)
            .order_by(AgentEventRecord.timestamp)
        )
        result = await self.session.execute(statement)
        events = list(result.scalars().all())

        return [
            {
                "id": evt.id,
                "event_type": evt.event_type.value,
                "agent_id": evt.agent_id,
                "parent_agent_id": evt.parent_agent_id,
                "depth": evt.depth,
                "data": json.loads(evt.data_json) if evt.data_json else {},
                "timestamp": evt.timestamp.isoformat() if evt.timestamp else None,
            }
            for evt in events
        ]
