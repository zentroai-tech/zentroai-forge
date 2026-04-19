"""Flow executor for running agent flows."""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import RunRecord, RunStatus, StepRecord, StepStatus
from agent_compiler.models.ir import FlowIR, NodeType, parse_ir
from agent_compiler.models.ir_v2 import FlowIRv2
from agent_compiler.models.credentials import CredentialProvider
from agent_compiler.observability.logging import StepLogger, get_logger
from agent_compiler.observability.tracing import create_span
from agent_compiler.runtime.context import ExecutionContext
from agent_compiler.runtime.node_handlers import execute_node
from agent_compiler.services.credential_service import CredentialService

logger = get_logger(__name__)

# Type alias for step event callbacks used by the SSE streaming endpoint.
# event_type: step_started | step_completed | step_failed | run_completed | run_failed
StepEventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class FlowExecutor:
    """Executor for running agent flows."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._credential_service = CredentialService(session)

    async def _resolve_env_vars(
        self,
        flow_id: str,
        profile: str = "development",
    ) -> dict[str, str]:
        """Load environment variables for a flow from the database.

        Args:
            flow_id: Flow ID to load vars for
            profile: Environment profile (development, staging, production)

        Returns:
            Dictionary mapping variable name to value
        """
        from sqlmodel import select
        from agent_compiler.models.db import FlowEnvVar

        try:
            from agent_compiler.services.encryption_service import (
                decrypt_secret,
                is_encryption_configured,
                EncryptionError,
                MasterKeyNotConfiguredError,
            )

            stmt = select(FlowEnvVar).where(
                FlowEnvVar.flow_id == flow_id,
                FlowEnvVar.profile == profile,
            )
            result = await self.session.exec(stmt)
            env_vars: dict[str, str] = {}
            for row in result.all():
                value = row.value
                if row.is_secret and value and is_encryption_configured():
                    try:
                        value = decrypt_secret(value)
                    except (EncryptionError, MasterKeyNotConfiguredError):
                        # Graceful fallback: legacy plaintext data before migration
                        logger.warning(
                            f"Could not decrypt env var '{row.key}' for flow {flow_id}; "
                            "using raw value (may be legacy plaintext)"
                        )
                env_vars[row.key] = value
            if env_vars:
                logger.info(f"Loaded {len(env_vars)} env vars for flow {flow_id} (profile={profile})")
            return env_vars
        except Exception as e:
            logger.warning(f"Could not load env vars: {e}")
            return {}

    async def _resolve_credentials(
        self,
        project_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, str]:
        """Resolve API keys for all providers.

        Uses the credential resolution precedence:
        1. Project credential
        2. Workspace credential
        3. Environment variable fallback

        Returns:
            Dictionary mapping provider name to API key
        """
        credentials: dict[str, str] = {}

        for provider in CredentialProvider:
            try:
                api_key = await self._credential_service.resolve_credential(
                    provider=provider,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    allow_env_fallback=True,
                )
                credentials[provider.value] = api_key
                logger.debug(f"Resolved credential for {provider.value}")
            except Exception:
                # Credential not found for this provider - that's OK
                # It will fail when the node actually needs it
                pass

        return credentials

    def _generate_run_id(self, flow_id: str) -> str:
        """Generate a deterministic-ish run ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"run_{flow_id}_{timestamp}_{short_uuid}"

    def _generate_step_id(self, run_id: str, node_id: str, order: int) -> str:
        """Generate a unique step ID (nonce prevents collisions on retry/fallback)."""
        nonce = uuid.uuid4().hex[:6]
        return f"{run_id}_step_{order}_{node_id}_{nonce}"

    async def create_run(
        self,
        flow_ir: FlowIR | FlowIRv2,
        input_data: dict[str, Any],
    ) -> RunRecord:
        """Create a new run record."""
        run_id = self._generate_run_id(flow_ir.flow.id)

        run = RunRecord(
            id=run_id,
            flow_id=flow_ir.flow.id,
            status=RunStatus.PENDING,
            input_json=json.dumps(input_data),
            ir_snapshot_json=flow_ir.model_dump_json(),
        )

        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)

        logger.info(f"Created run: {run_id}")
        return run

    async def execute(
        self,
        flow_ir: FlowIR,
        input_data: dict[str, Any],
        run: RunRecord | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
        entrypoint: str | None = None,
    ) -> RunRecord:
        """Execute a flow with the given input.

        Delegates FlowIRv2 execution to AgentExecutor.

        Args:
            flow_ir: The IR v2 flow to execute
            input_data: Input data for the run
            run: Optional existing run record (for replay)
            project_id: Optional project ID for credential resolution
            workspace_id: Optional workspace ID for credential resolution

        Returns:
            The completed run record
        """
        # Delegate IR v2 execution to AgentExecutor
        if hasattr(flow_ir, "agents"):
            from agent_compiler.runtime.agent_executor import AgentExecutor

            agent_executor = AgentExecutor(self.session)
            return await agent_executor.execute(
                ir=flow_ir,
                input_data=input_data,
                entrypoint=entrypoint or "main",
                run=run,
                project_id=project_id,
                workspace_id=workspace_id,
            )

        # Create run if not provided
        if run is None:
            run = await self.create_run(flow_ir, input_data)

        # Update run status
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        self.session.add(run)
        await self.session.commit()

        # Resolve credentials for the run
        # Use flow ID as project_id if not explicitly provided
        resolved_project_id = project_id or flow_ir.flow.id
        credentials = await self._resolve_credentials(
            project_id=resolved_project_id,
            workspace_id=workspace_id,
        )

        # Load environment variables for this flow
        env_vars = await self._resolve_env_vars(flow_ir.flow.id)

        # Initialize execution context with resolved credentials and env vars
        context: ExecutionContext | None = ExecutionContext(
            user_input=input_data,
            resolved_credentials=credentials,
            env_vars=env_vars,
        )

        # Get topological order
        execution_order = flow_ir.get_topological_order()
        logger.info(f"Executing flow in order: {execution_order}")

        try:
            with create_span("flow_execution", {"flow_id": flow_ir.flow.id, "run_id": run.id}):
                for order, node_id in enumerate(execution_order):
                    node = flow_ir.get_node(node_id)
                    if node is None:
                        raise ValueError(f"Node not found: {node_id}")

                    step = await self._execute_step(
                        run=run,
                        node=node,
                        order=order,
                        context=context,
                        flow_ir=flow_ir,
                    )

                    # Handle router node (modify execution path)
                    if node.type == NodeType.ROUTER and step.output_data:
                        selected_route = step.output_data.get("selected_route")
                        if selected_route:
                            context.variables["_next_node"] = selected_route

            # Run completed successfully
            run.status = RunStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)
            run.output_json = json.dumps(context.to_dict())

        except Exception as e:
            logger.error(f"Run failed: {e}")
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(e)
            raise

        finally:
            if context is not None:
                await context.close_external_resources()
            self.session.add(run)
            await self.session.commit()
            await self.session.refresh(run)

        return run

    async def execute_streaming(
        self,
        flow_ir: FlowIR,
        input_data: dict[str, Any],
        on_event: StepEventCallback,
        project_id: str | None = None,
        workspace_id: str | None = None,
        entrypoint: str | None = None,
    ) -> RunRecord:
        """Execute a flow and emit SSE events via the callback for each step.

        Delegates FlowIRv2 streaming execution to AgentExecutor.

        Args:
            flow_ir: The IR v2 flow to execute
            input_data: Input data for the run
            on_event: Async callback(event_type, payload) for SSE events
            project_id: Project ID for credential resolution
            workspace_id: Workspace ID for credential resolution

        Returns:
            The completed run record
        """
        # Delegate IR v2 execution to AgentExecutor
        if hasattr(flow_ir, "agents"):
            from agent_compiler.runtime.agent_executor import AgentExecutor

            agent_executor = AgentExecutor(self.session)
            return await agent_executor.execute(
                ir=flow_ir,
                input_data=input_data,
                entrypoint=entrypoint or "main",
                project_id=project_id,
                workspace_id=workspace_id,
                on_event=on_event,
            )

        run = await self.create_run(flow_ir, input_data)
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        self.session.add(run)
        await self.session.commit()

        resolved_project_id = project_id or flow_ir.flow.id
        credentials = await self._resolve_credentials(
            project_id=resolved_project_id,
            workspace_id=workspace_id,
        )

        # Load environment variables
        env_vars = await self._resolve_env_vars(flow_ir.flow.id)

        context: ExecutionContext | None = ExecutionContext(
            user_input=input_data,
            resolved_credentials=credentials,
            env_vars=env_vars,
        )
        execution_order = flow_ir.get_topological_order()

        try:
            for order, node_id in enumerate(execution_order):
                node = flow_ir.get_node(node_id)
                if node is None:
                    raise ValueError(f"Node not found: {node_id}")

                await on_event("step_started", {
                    "run_id": run.id,
                    "node_id": node.id,
                    "node_type": node.type.value,
                    "order": order,
                })

                step = await self._execute_step(
                    run=run,
                    node=node,
                    order=order,
                    context=context,
                    flow_ir=flow_ir,
                )

                output = json.loads(step.output_json) if step.output_json else None
                duration_ms = None
                if step.started_at and step.finished_at:
                    duration_ms = (step.finished_at - step.started_at).total_seconds() * 1000

                await on_event("step_completed", {
                    "run_id": run.id,
                    "node_id": node.id,
                    "node_type": node.type.value,
                    "order": order,
                    "output": output,
                    "duration_ms": duration_ms,
                })

                if node.type == NodeType.ROUTER and step.output_data:
                    selected_route = step.output_data.get("selected_route")
                    if selected_route:
                        context.variables["_next_node"] = selected_route

            run.status = RunStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)
            run.output_json = json.dumps(context.to_dict())

            await on_event("run_completed", {
                "run_id": run.id,
                "status": "completed",
            })

        except Exception as e:
            logger.error(f"Streaming run failed: {e}")
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(e)

            await on_event("step_failed", {
                "run_id": run.id,
                "error": str(e),
            })
            await on_event("run_failed", {
                "run_id": run.id,
                "status": "failed",
                "error": str(e),
            })

        finally:
            if context is not None:
                await context.close_external_resources()
            self.session.add(run)
            await self.session.commit()
            await self.session.refresh(run)

        return run

    async def _execute_step(
        self,
        run: RunRecord,
        node: Any,
        order: int,
        context: ExecutionContext,
        flow_ir: FlowIR,
    ) -> StepRecord:
        """Execute a single step in the flow, with optional retry and timeout."""
        step_id = self._generate_step_id(run.id, node.id, order)
        step_logger = StepLogger(run.id, step_id, node.id, node.type.value)

        # Create step record
        step = StepRecord(
            id=step_id,
            run_id=run.id,
            node_id=node.id,
            node_type=node.type.value,
            step_order=order,
            status=StepStatus.RUNNING,
            input_json=json.dumps(context.to_dict()),
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(step)
        await self.session.commit()

        step_logger.step_started(context.to_dict())
        start_time = time.time()

        # Extract retry/timeout config from node params
        retry_count = 0
        retry_delay = 1.0
        timeout_seconds = None
        params = node.params if isinstance(node.params, dict) else {}
        retry_count = params.get("retry_count", 0)
        retry_delay = params.get("retry_delay", 1.0)
        timeout_seconds = params.get("timeout_seconds")

        try:
            with create_span(f"node_{node.type.value}", {"node_id": node.id}):
                # Execute with retry logic
                last_error = None
                for attempt in range(max(1, retry_count + 1)):
                    try:
                        if node.type == NodeType.PARALLEL:
                            context.variables[f"_parallel_successors::{node.id}"] = flow_ir.get_successors(node.id)
                        elif node.type == NodeType.JOIN:
                            context.variables[f"_join_predecessors::{node.id}"] = flow_ir.get_predecessors(node.id)

                        coro = execute_node(
                            node=node,
                            context=context,
                            flow_engine=flow_ir.flow.engine_preference,
                            logger=step_logger,
                        )
                        if timeout_seconds and timeout_seconds > 0:
                            output = await asyncio.wait_for(coro, timeout=timeout_seconds)
                        else:
                            output = await coro
                        break  # success
                    except asyncio.TimeoutError:
                        last_error = TimeoutError(
                            f"Node {node.id} timed out after {timeout_seconds}s (attempt {attempt + 1}/{retry_count + 1})"
                        )
                        if attempt < retry_count:
                            logger.warning(f"Node {node.id} timed out, retrying in {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                    except Exception as e:
                        last_error = e
                        if attempt < retry_count:
                            logger.warning(f"Node {node.id} failed: {e}, retrying in {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                else:
                    # All attempts exhausted
                    raise last_error or RuntimeError(f"Node {node.id} failed after {retry_count + 1} attempts")

            # Update context with output
            context.set_node_output(node.id, output)

            # Update step record
            step.status = StepStatus.COMPLETED
            step.finished_at = datetime.now(timezone.utc)
            step.output_json = json.dumps(output)

            # Token tracking for LLM nodes
            if node.type == NodeType.LLM and isinstance(output, dict):
                step.model_name = output.get("model")
                tokens = output.get("tokens_used")
                if tokens is not None:
                    if isinstance(tokens, dict):
                        step.tokens_input = tokens.get("input") or tokens.get("prompt_tokens")
                        step.tokens_output = tokens.get("output") or tokens.get("completion_tokens")
                        step.tokens_total = tokens.get("total") or (
                            (step.tokens_input or 0) + (step.tokens_output or 0)
                        )
                    elif isinstance(tokens, (int, float)):
                        step.tokens_total = int(tokens)

            # Emit debug timeline events
            from agent_compiler.services.event_recorder import EventRecorder
            recorder = EventRecorder(self.session, run.id)
            await recorder.record_step(
                node_id=node.id,
                node_type=node.type.value,
                input_data=json.loads(step.input_json) if step.input_json else {},
                output_data=output,
            )

            duration_ms = (time.time() - start_time) * 1000
            step_logger.step_completed(output, duration_ms)

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            step.status = StepStatus.FAILED
            step.finished_at = datetime.now(timezone.utc)
            step.error_message = str(e)
            step_logger.step_failed(str(e), duration_ms)
            raise

        finally:
            self.session.add(step)
            await self.session.commit()
            await self.session.refresh(step)

        return step

    async def replay_run(self, run_id: str) -> RunRecord:
        """Replay a run using its stored IR snapshot.

        Args:
            run_id: The ID of the run to replay

        Returns:
            A new run record with the replay results
        """
        # Fetch original run
        from sqlmodel import select

        statement = select(RunRecord).where(RunRecord.id == run_id)
        result = await self.session.exec(statement)
        original_run = result.one_or_none()

        if original_run is None:
            raise ValueError(f"Run not found: {run_id}")

        # Parse the IR snapshot (v2-only)
        flow_ir = parse_ir(json.loads(original_run.ir_snapshot_json))

        # Parse original input
        input_data = json.loads(original_run.input_json)

        # Execute with the same IR and input
        return await self.execute(flow_ir, input_data)

    async def execute_with_mocks(
        self,
        flow_ir: FlowIR,
        input_data: dict[str, Any],
        run: RunRecord,
        mocks: dict[str, dict[str, Any]],
        project_id: str | None = None,
        workspace_id: str | None = None,
    ) -> RunRecord:
        """Execute a flow with mocked node outputs.

        Args:
            flow_ir: The flow IR to execute
            input_data: Input data for the run
            run: The run record (already created)
            mocks: Dictionary mapping node_id to mock outputs
            project_id: Optional project ID for credential resolution
            workspace_id: Optional workspace ID for credential resolution

        Returns:
            The completed run record
        """
        # Update run status
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        self.session.add(run)
        await self.session.commit()

        # Resolve credentials (same as execute())
        resolved_project_id = project_id or flow_ir.flow.id
        credentials = await self._resolve_credentials(
            project_id=resolved_project_id,
            workspace_id=workspace_id,
        )

        # Load environment variables
        env_vars = await self._resolve_env_vars(flow_ir.flow.id)

        # Initialize execution context with resolved credentials and env vars
        context: ExecutionContext | None = ExecutionContext(
            user_input=input_data,
            resolved_credentials=credentials,
            env_vars=env_vars,
        )

        # Get topological order
        execution_order = flow_ir.get_topological_order()
        logger.info(f"Executing flow with mocks, order: {execution_order}")

        try:
            with create_span("flow_execution_mocked", {"flow_id": flow_ir.flow.id, "run_id": run.id}):
                for order, node_id in enumerate(execution_order):
                    node = flow_ir.get_node(node_id)
                    if node is None:
                        raise ValueError(f"Node not found: {node_id}")

                    # Check if this node should be mocked
                    if node_id in mocks:
                        step = await self._execute_mocked_step(
                            run=run,
                            node=node,
                            order=order,
                            context=context,
                            mock_output=mocks[node_id],
                        )
                    else:
                        step = await self._execute_step(
                            run=run,
                            node=node,
                            order=order,
                            context=context,
                            flow_ir=flow_ir,
                        )

                    # Handle router node (modify execution path)
                    if node.type == NodeType.ROUTER and step.output_data:
                        selected_route = step.output_data.get("selected_route")
                        if selected_route:
                            context.variables["_next_node"] = selected_route

            # Run completed successfully
            run.status = RunStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)
            run.output_json = json.dumps(context.to_dict())

        except Exception as e:
            logger.error(f"Mocked run failed: {e}")
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(e)
            raise

        finally:
            if context is not None:
                await context.close_external_resources()
            self.session.add(run)
            await self.session.commit()
            await self.session.refresh(run)

        return run

    async def _execute_mocked_step(
        self,
        run: RunRecord,
        node: Any,
        order: int,
        context: ExecutionContext,
        mock_output: dict[str, Any],
    ) -> StepRecord:
        """Execute a mocked step (return stored output instead of running node)."""
        step_id = self._generate_step_id(run.id, node.id, order)
        step_logger = StepLogger(run.id, step_id, node.id, node.type.value)

        # Create step record
        step = StepRecord(
            id=step_id,
            run_id=run.id,
            node_id=node.id,
            node_type=node.type.value,
            step_order=order,
            status=StepStatus.RUNNING,
            input_json=json.dumps(context.to_dict()),
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(step)
        await self.session.commit()

        step_logger.step_started(context.to_dict())
        start_time = time.time()

        try:
            # Use mocked output instead of executing
            output = mock_output
            logger.info(f"Using mocked output for node {node.id}")

            # Update context with output
            context.set_node_output(node.id, output)

            # Update step record
            step.status = StepStatus.COMPLETED
            step.finished_at = datetime.now(timezone.utc)
            step.output_json = json.dumps(output)
            step.meta_json = json.dumps({"mocked": True})

            duration_ms = (time.time() - start_time) * 1000
            step_logger.step_completed(output, duration_ms)

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            step.status = StepStatus.FAILED
            step.finished_at = datetime.now(timezone.utc)
            step.error_message = str(e)
            step_logger.step_failed(str(e), duration_ms)
            raise

        finally:
            self.session.add(step)
            await self.session.commit()
            await self.session.refresh(step)

        return step
