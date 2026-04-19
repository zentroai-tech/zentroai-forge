"""Deterministic replay service for flow executions.

Supports replaying runs with:
- Exact artifact replay (all external calls mocked)
- Tool-only mocking (re-run LLMs, mock tools)
- Custom mock overrides per node
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import (
    ArtifactType,
    ReplayConfig,
    ReplayMode,
    RunRecord,
    RunStatus,
    StepArtifact,
    StepRecord,
)
from agent_compiler.models.ir import NodeType, parse_ir
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class ReplayService:
    """Service for deterministic replay of flow executions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def capture_artifact(
        self,
        step: StepRecord,
        artifact_type: ArtifactType,
        data: dict[str, Any],
    ) -> StepArtifact:
        """Capture an artifact from step execution.

        Args:
            step: The step record
            artifact_type: Type of artifact
            data: Artifact data to store

        Returns:
            The created artifact record
        """
        artifact = StepArtifact(
            id=f"{step.id}_artifact_{uuid.uuid4().hex[:8]}",
            step_id=step.id,
            artifact_type=artifact_type,
            artifact_json=json.dumps(data),
            created_at=datetime.now(timezone.utc),
        )

        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)

        logger.debug(f"Captured artifact {artifact.id} for step {step.id}")
        return artifact

    async def get_step_artifacts(
        self,
        step_id: str,
        artifact_type: ArtifactType | None = None,
    ) -> list[StepArtifact]:
        """Get artifacts for a step.

        Args:
            step_id: The step ID
            artifact_type: Optional filter by artifact type

        Returns:
            List of artifacts
        """
        statement = select(StepArtifact).where(StepArtifact.step_id == step_id)
        if artifact_type:
            statement = statement.where(StepArtifact.artifact_type == artifact_type)

        result = await self.session.exec(statement)
        return list(result.all())

    async def get_run_artifacts(self, run_id: str) -> dict[str, list[dict[str, Any]]]:
        """Get all artifacts for a run, organized by step.

        Args:
            run_id: The run ID

        Returns:
            Dictionary mapping step_id to list of artifacts
        """
        # Get all steps for the run
        statement = select(StepRecord).where(StepRecord.run_id == run_id)
        result = await self.session.exec(statement)
        steps = list(result.all())

        artifacts_by_step: dict[str, list[dict[str, Any]]] = {}

        for step in steps:
            step_artifacts = await self.get_step_artifacts(step.id)
            artifacts_by_step[step.node_id] = [
                {
                    "type": a.artifact_type.value,
                    "data": a.artifact_data,
                    "created_at": a.created_at.isoformat(),
                }
                for a in step_artifacts
            ]

        return artifacts_by_step

    async def build_mock_context(
        self,
        run_id: str,
        config: ReplayConfig,
    ) -> dict[str, dict[str, Any]]:
        """Build mock context for replay.

        Args:
            run_id: The original run ID
            config: Replay configuration

        Returns:
            Dictionary mapping node_id to mock outputs
        """
        mocks: dict[str, dict[str, Any]] = {}

        # Get all steps and their artifacts
        statement = (
            select(StepRecord)
            .where(StepRecord.run_id == run_id)
            .order_by(StepRecord.step_order)
        )
        result = await self.session.exec(statement)
        steps = list(result.all())

        for step in steps:
            node_id = step.node_id
            scoped_node_id = (
                f"{step.agent_id}::{step.node_id}"
                if getattr(step, "agent_id", None)
                else node_id
            )

            # Check for manual override
            if node_id in config.mock_overrides:
                mocks[node_id] = config.mock_overrides[node_id]
                continue
            if scoped_node_id in config.mock_overrides:
                mocks[scoped_node_id] = config.mock_overrides[scoped_node_id]
                continue

            # Skip if node is in skip list
            if node_id in config.skip_nodes:
                continue

            # Determine what to mock based on mode
            if config.mode == ReplayMode.EXACT:
                # Mock everything - use stored output
                if step.output_json:
                    mocks[scoped_node_id] = json.loads(step.output_json)
            elif config.mode == ReplayMode.MOCK_TOOLS:
                # Only mock tool calls
                if step.node_type == NodeType.TOOL.value:
                    if step.output_json:
                        mocks[scoped_node_id] = json.loads(step.output_json)
            elif config.mode == ReplayMode.MOCK_ALL:
                # Mock all external calls (tools, LLMs, retrievers)
                if step.node_type in (
                    NodeType.TOOL.value,
                    NodeType.LLM.value,
                    NodeType.RETRIEVER.value,
                ):
                    if step.output_json:
                        mocks[scoped_node_id] = json.loads(step.output_json)

        return mocks

    async def replay_run(
        self,
        run_id: str,
        config: ReplayConfig | None = None,
    ) -> RunRecord:
        """Replay a run with optional mocking.

        Args:
            run_id: The ID of the run to replay
            config: Replay configuration (defaults to EXACT mode)

        Returns:
            A new run record with replay results
        """
        from agent_compiler.models.db import FlowRecord
        from agent_compiler.runtime.executor import FlowExecutor

        if config is None:
            config = ReplayConfig(mode=ReplayMode.EXACT)

        # Fetch original run
        statement = select(RunRecord).where(RunRecord.id == run_id)
        result = await self.session.exec(statement)
        original_run = result.one_or_none()

        if original_run is None:
            raise ValueError(f"Run not found: {run_id}")

        # For EXACT mode (re-runs everything live), use the CURRENT flow IR
        # so that config changes (e.g. model/provider) take effect.
        # For mock modes, use the snapshot IR since mocks are tied to the
        # original node structure.
        if config.mode == ReplayMode.EXACT:
            flow_stmt = select(FlowRecord).where(
                FlowRecord.id == original_run.flow_id
            )
            flow_result = await self.session.exec(flow_stmt)
            flow_record = flow_result.one_or_none()

            if flow_record is not None:
                flow_ir = parse_ir(json.loads(flow_record.ir_json))
                logger.info(
                    f"Replay EXACT: using current flow IR for {original_run.flow_id}"
                )
            else:
                # Flow deleted — fall back to snapshot
                flow_ir = parse_ir(json.loads(original_run.ir_snapshot_json))
                logger.warning(
                    f"Replay EXACT: flow {original_run.flow_id} not found, "
                    f"falling back to run snapshot"
                )
        else:
            flow_ir = parse_ir(json.loads(original_run.ir_snapshot_json))

        # Parse original input
        input_data = json.loads(original_run.input_json)

        # Build mock context
        mocks = await self.build_mock_context(run_id, config)

        logger.info(
            f"Replaying run {run_id} with mode={config.mode.value}, "
            f"mocking {len(mocks)} nodes"
        )

        executor = FlowExecutor(self.session)
        replay_run = await executor.create_run(flow_ir, input_data)
        replay_run.meta_json = json.dumps({
            "replay_of": run_id,
            "replay_mode": config.mode.value,
            "mocked_nodes": list(mocks.keys()),
            "used_current_ir": config.mode == ReplayMode.EXACT,
        })

        # Execute — EXACT mode has no mocks, mock modes use stored artifacts
        from agent_compiler.runtime.agent_executor import AgentExecutor

        agent_executor = AgentExecutor(self.session)
        if config.mode == ReplayMode.EXACT and not mocks:
            return await agent_executor.execute(
                flow_ir,
                input_data,
                entrypoint=getattr(original_run, "entrypoint", "main") or "main",
                run=replay_run,
            )
        return await agent_executor.execute(
            flow_ir,
            input_data,
            entrypoint=getattr(original_run, "entrypoint", "main") or "main",
            run=replay_run,
            mocks=mocks,
        )


# Artifact type mapping for node types
NODE_TYPE_TO_ARTIFACT: dict[str, ArtifactType] = {
    NodeType.LLM.value: ArtifactType.LLM_RESPONSE,
    NodeType.TOOL.value: ArtifactType.TOOL_OUTPUT,
    NodeType.RETRIEVER.value: ArtifactType.RETRIEVAL_RESULT,
    NodeType.ROUTER.value: ArtifactType.ROUTER_DECISION,
}
