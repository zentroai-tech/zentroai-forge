"""Multi-agent executor for IR v2 flows.

Orchestrates multiple agents with handoff support, budget enforcement,
and tool isolation. Reuses FlowExecutor._execute_step() for node execution.
"""

from __future__ import annotations

import json
from copy import deepcopy
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import (
    AgentEventRecord,
    RunRecord,
    RunStatus,
    StepRecord,
    TimelineEventType,
)
from agent_compiler.models.ir import Flow, NodeType, RetrySpec, SchemaRef
from agent_compiler.models.ir_v2 import (
    FlowIRv2,
    AgentSpec,
    HandoffMode,
    HandoffRule,
)
from agent_compiler.models.ir_v2_1_defaults import merge_policy
from agent_compiler.observability.logging import get_logger
from agent_compiler.runtime.agent_context import AgentRunContext, BudgetExceededError
from agent_compiler.runtime.context import ExecutionContext
from agent_compiler.runtime.executor import FlowExecutor, StepEventCallback
from agent_compiler.runtime.graph_runtime import AgentGraphRuntime
from agent_compiler.services.credential_service import CredentialService
from agent_compiler.services.policy_guard import (
    apply_redaction,
    sanitize_input,
    validate_handoff,
    validate_tool_call,
)
from agent_compiler.services.retry_runtime import run_with_retry
from agent_compiler.services.schema_validation import (
    SchemaValidationError,
    validate_payload_or_raise,
)

logger = get_logger(__name__)


class AgentExecutor:
    """Executor for multi-agent (IR v2) flows."""

    MAX_GLOBAL_DEPTH = 10
    BUDGET_WARNING_THRESHOLD = 0.8

    def __init__(self, session: AsyncSession):
        self.session = session
        self._credential_service = CredentialService(session)
        self._flow_executor = FlowExecutor(session)

    async def execute(
        self,
        ir: FlowIRv2,
        input_data: dict[str, Any],
        entrypoint: str = "main",
        run: RunRecord | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
        on_event: StepEventCallback | None = None,
        mocks: dict[str, dict[str, Any]] | None = None,
    ) -> RunRecord:
        """Execute a multi-agent flow.

        Args:
            ir: The v2 flow IR
            input_data: Input data for the run
            entrypoint: Name of the entrypoint to use
            run: Optional existing run record
            project_id: Optional project ID for credential resolution
            workspace_id: Optional workspace ID for credential resolution
            on_event: Optional SSE event callback

        Returns:
            The completed run record
        """
        # Resolve entrypoint
        ep = ir.get_entrypoint(entrypoint)
        if ep is None:
            raise ValueError(f"Entrypoint '{entrypoint}' not found")

        # Create run if not provided
        if run is None:
            run = await self._flow_executor.create_run(ir, input_data)
            run.entrypoint = entrypoint

        # Update run status
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        self.session.add(run)
        await self.session.commit()

        # Resolve credentials and env vars
        resolved_project_id = project_id or ir.flow.id
        credentials = await self._flow_executor._resolve_credentials(
            project_id=resolved_project_id,
            workspace_id=workspace_id,
        )
        env_vars = await self._flow_executor._resolve_env_vars(ir.flow.id)

        # Create root execution context
        context: ExecutionContext | None = ExecutionContext(
            user_input=input_data,
            resolved_credentials=credentials,
            env_vars=env_vars,
        )

        try:
            result = await self.call_agent(
                ir=ir,
                agent_id=ep.agent_id,
                input_data=input_data,
                context=context,
                run=run,
                parent_ctx=None,
                depth=0,
                on_event=on_event,
                mocks=mocks,
            )

            run.status = RunStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)
            run.output_json = json.dumps(result)

            if on_event:
                await on_event("run_completed", {"run_id": run.id, "status": "completed"})

        except Exception as e:
            logger.error(f"Multi-agent run failed: {e}")
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(e)

            if on_event:
                await on_event("run_failed", {"run_id": run.id, "status": "failed", "error": str(e)})

            raise
        finally:
            if context is not None:
                await context.close_external_resources()
            self.session.add(run)
            await self.session.commit()
            await self.session.refresh(run)

        return run

    async def call_agent(
        self,
        ir: FlowIRv2,
        agent_id: str,
        input_data: dict[str, Any],
        context: ExecutionContext,
        run: RunRecord,
        parent_ctx: AgentRunContext | None,
        depth: int,
        on_event: StepEventCallback | None = None,
        mocks: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Execute a single agent's graph.

        Args:
            ir: The v2 flow IR
            agent_id: Agent to execute
            input_data: Input data for this agent
            context: The execution context
            run: The run record
            parent_ctx: Parent agent context (for nested calls)
            depth: Current nesting depth
            on_event: Optional SSE event callback

        Returns:
            Agent output as a dictionary
        """
        # Depth check
        if depth >= self.MAX_GLOBAL_DEPTH:
            raise RuntimeError(
                f"Maximum global depth ({self.MAX_GLOBAL_DEPTH}) exceeded at agent '{agent_id}'"
            )

        agent = ir.get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Agent '{agent_id}' not found")

        # Per-agent depth check
        if depth >= agent.budgets.max_depth:
            raise RuntimeError(
                f"Agent '{agent_id}' max_depth ({agent.budgets.max_depth}) exceeded"
            )

        # Build agent context
        agent_ctx = AgentRunContext(
            agent_id=agent_id,
            run_id=run.id,
            parent_run_context=parent_ctx,
            depth=depth,
            memory_namespace=agent.memory_namespace,
            tools_allowlist=agent.tools_allowlist,
            budgets=agent.budgets,
            policies=merge_policy(ir.policies, agent.policies),
            retries=agent.retries,
            fallbacks=agent.fallbacks,
        )

        # Apply input sanitization policy for this agent.
        sanitized_input = dict(input_data)
        raw_text_input = sanitized_input.get("input")
        if isinstance(raw_text_input, str) and agent_ctx.policies is not None:
            sanitized_input["input"] = sanitize_input(raw_text_input, agent_ctx.policies)

        # Emit AGENT_START event
        await self._emit_event(
            run.id, TimelineEventType.AGENT_START, agent_id, depth,
            parent_ctx, {"input": sanitized_input}
        )

        if on_event:
            await on_event("agent_start", {
                "run_id": run.id, "agent_id": agent_id, "depth": depth,
            })

        runtime_graph = AgentGraphRuntime(
            flow=Flow(
                id=f"{ir.flow.id}__{agent_id}",
                name=agent.name,
                version=ir.flow.version,
                engine_preference=ir.flow.engine_preference,
                description=ir.flow.description,
            ),
            nodes=agent.graph.nodes,
            edges=agent.graph.edges,
        )

        # Execute topologically
        execution_order = runtime_graph.get_topological_order()
        step_order_base = agent_ctx.steps_executed
        budget_warnings_emitted: set[str] = set()

        try:
            for order, node_id in enumerate(execution_order):
                node = runtime_graph.get_node(node_id)
                if node is None:
                    raise ValueError(f"Node not found: {node_id}")

                # Budget check before step
                agent_ctx.check_budget()

                # Enforce tool policy (allow/deny)
                if node.type == NodeType.TOOL:
                    tool_name = node.params.get("tool_name", "")
                    decision = validate_tool_call(
                        policy=agent_ctx.policies or ir.policies,
                        agent_allowlist=agent_ctx.tools_allowlist,
                        tool_name=tool_name,
                    )
                    if not decision.allowed:
                        await self._emit_event(
                            run.id,
                            TimelineEventType.GUARD_BLOCK,
                            agent_id,
                            depth,
                            parent_ctx,
                            {
                                "guard_type": "tool",
                                "tool_name": tool_name,
                                "reason": decision.reason,
                                "code": decision.code,
                            },
                        )
                        raise RuntimeError(decision.reason or f"Tool '{tool_name}' blocked by policy")

                if on_event:
                    await on_event("step_started", {
                        "run_id": run.id, "node_id": node.id,
                        "node_type": node.type.value, "order": order,
                        "agent_id": agent_id,
                    })

                mock_key = f"{agent_id}::{node.id}"
                mock_output = None
                if mocks:
                    mock_output = mocks.get(mock_key) or mocks.get(node.id)

                if mock_output is not None:
                    step = await self._flow_executor._execute_mocked_step(
                        run=run,
                        node=node,
                        order=step_order_base + order,
                        context=context,
                        mock_output=mock_output,
                    )
                    step.agent_id = agent_ctx.agent_id
                    step.depth = agent_ctx.depth
                    if agent_ctx.parent_run_context:
                        step.parent_step_id = f"agent_{agent_ctx.parent_run_context.agent_id}"
                    self.session.add(step)
                    await self.session.commit()
                else:
                    # Execute the step using FlowExecutor's existing logic
                    step = await self._execute_agent_step(
                        run=run,
                        node=node,
                        order=step_order_base + order,
                        context=context,
                        flow_ir=runtime_graph,
                        agent_ctx=agent_ctx,
                        agent=agent,
                        schema_contracts=ir.resources.schema_contracts,
                    )

                if on_event:
                    output = json.loads(step.output_json) if step.output_json else None
                    await on_event("step_completed", {
                        "run_id": run.id, "node_id": node.id,
                        "node_type": node.type.value, "order": order,
                        "output": output, "agent_id": agent_id,
                    })

                # Track budget consumption
                agent_ctx.steps_executed += 1
                if node.type == NodeType.LLM and step.tokens_total:
                    agent_ctx.tokens_used += step.tokens_total
                if node.type == NodeType.TOOL:
                    agent_ctx.tool_calls_made += 1

                # Emit proactive budget warnings once per resource type.
                await self._emit_budget_warnings(
                    run_id=run.id,
                    agent_ctx=agent_ctx,
                    depth=depth,
                    parent_ctx=parent_ctx,
                    emitted=budget_warnings_emitted,
                )

                # Check router output for handoff
                if node.type == NodeType.ROUTER and step.output_data:
                    selected_route = step.output_data.get("selected_route")
                    if selected_route:
                        context.variables["_next_node"] = selected_route
                        # Check for handoff match
                        handoff = self._find_handoff(ir, agent_id, selected_route)
                        if handoff:
                            handoff_result = await self._execute_handoff(
                                ir, handoff, context, run, agent_ctx, depth, on_event, mocks
                            )
                            context.set_node_output(f"_handoff_{handoff.to_agent_id}", handoff_result)
        except BudgetExceededError as e:
            await self._emit_event(
                run.id,
                TimelineEventType.BUDGET_EXCEEDED,
                agent_id,
                depth,
                parent_ctx,
                {
                    "budget_type": e.resource,
                    "used": e.used,
                    "limit": e.limit,
                    "agent_id": agent_id,
                    "message": str(e),
                },
            )
            raise

        # Emit AGENT_END event
        await self._emit_event(
            run.id, TimelineEventType.AGENT_END, agent_id, depth,
            parent_ctx, {"steps_executed": agent_ctx.steps_executed}
        )

        if on_event:
            await on_event("agent_end", {
                "run_id": run.id, "agent_id": agent_id, "depth": depth,
            })

        return context.to_dict()

    async def _execute_handoff(
        self,
        ir: FlowIRv2,
        handoff: HandoffRule,
        context: ExecutionContext,
        run: RunRecord,
        parent_ctx: AgentRunContext,
        depth: int,
        on_event: StepEventCallback | None = None,
        mocks: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Execute a handoff to another agent."""
        # Emit HANDOFF event
        guard_decision = validate_handoff(
            from_agent=handoff.from_agent_id,
            to_agent=handoff.to_agent_id,
            payload=context.user_input,
        )
        if not guard_decision.allowed:
            await self._emit_event(
                run.id,
                TimelineEventType.GUARD_BLOCK,
                handoff.from_agent_id,
                depth,
                parent_ctx,
                {
                    "guard_type": "handoff",
                    "from_agent": handoff.from_agent_id,
                    "to_agent": handoff.to_agent_id,
                    "reason": guard_decision.reason,
                    "code": guard_decision.code,
                },
            )
            raise RuntimeError(guard_decision.reason or "Handoff blocked by guard policy")

        policy = parent_ctx.policies if parent_ctx and parent_ctx.policies else ir.policies
        soft_fail = bool(policy.allow_schema_soft_fail)
        try:
            input_warning = validate_payload_or_raise(
                context.user_input if isinstance(context.user_input, dict) else {},
                handoff.input_schema,
                soft_fail=soft_fail,
                schema_contracts=ir.resources.schema_contracts,
            )
            if input_warning:
                await self._emit_event(
                    run.id,
                    TimelineEventType.SCHEMA_VALIDATION_ERROR,
                    handoff.from_agent_id,
                    depth,
                    parent_ctx,
                    {"phase": "handoff_input", "warning": input_warning},
                )
        except SchemaValidationError as exc:
            await self._emit_event(
                run.id,
                TimelineEventType.SCHEMA_VALIDATION_ERROR,
                handoff.from_agent_id,
                depth,
                parent_ctx,
                {"phase": "handoff_input", "error": str(exc)},
            )
            raise

        # Emit HANDOFF event
        await self._emit_event(
            run.id, TimelineEventType.HANDOFF, handoff.to_agent_id, depth + 1,
            parent_ctx, {
                "from_agent": handoff.from_agent_id,
                "to_agent": handoff.to_agent_id,
                "mode": handoff.mode.value,
            }
        )

        if on_event:
            await on_event("handoff", {
                "run_id": run.id,
                "from_agent": handoff.from_agent_id,
                "to_agent": handoff.to_agent_id,
                "mode": handoff.mode.value,
            })

        # Prepare context based on handoff mode
        if handoff.mode == HandoffMode.CALL:
            # CALL: shared context — child sees parent's node outputs
            child_context = context
        else:
            # DELEGATE: isolated context — fresh context
            child_context = ExecutionContext(
                user_input=context.user_input,
                resolved_credentials=context.resolved_credentials,
                env_vars=context.env_vars,
                mcp_sessions=context.mcp_sessions,
            )

        input_data = context.user_input

        result = await self.call_agent(
            ir=ir,
            agent_id=handoff.to_agent_id,
            input_data=input_data,
            context=child_context,
            run=run,
            parent_ctx=parent_ctx,
            depth=depth + 1,
            on_event=on_event,
            mocks=mocks,
        )

        output_payload = result if isinstance(result, dict) else {"result": result}
        try:
            output_warning = validate_payload_or_raise(
                output_payload,
                handoff.output_schema,
                soft_fail=soft_fail,
                schema_contracts=ir.resources.schema_contracts,
            )
            if output_warning:
                await self._emit_event(
                    run.id,
                    TimelineEventType.SCHEMA_VALIDATION_ERROR,
                    handoff.to_agent_id,
                    depth + 1,
                    parent_ctx,
                    {"phase": "handoff_output", "warning": output_warning},
                )
        except SchemaValidationError as exc:
            await self._emit_event(
                run.id,
                TimelineEventType.SCHEMA_VALIDATION_ERROR,
                handoff.to_agent_id,
                depth + 1,
                parent_ctx,
                {"phase": "handoff_output", "error": str(exc)},
            )
            raise

        if handoff.mode == HandoffMode.DELEGATE:
            return {"delegated_to": handoff.to_agent_id, "result": result}

        return result

    async def _emit_budget_warnings(
        self,
        run_id: str,
        agent_ctx: AgentRunContext,
        depth: int,
        parent_ctx: AgentRunContext | None,
        emitted: set[str],
    ) -> None:
        """Emit warning events when budget usage crosses the warning threshold."""
        usage_specs: tuple[tuple[str, int, int | None], ...] = (
            ("max_steps", agent_ctx.steps_executed, agent_ctx.budgets.max_steps),
            ("max_tokens", agent_ctx.tokens_used, agent_ctx.budgets.max_tokens),
            ("max_tool_calls", agent_ctx.tool_calls_made, agent_ctx.budgets.max_tool_calls),
        )

        for budget_type, used, limit in usage_specs:
            if limit is None or limit <= 0:
                continue
            if budget_type in emitted:
                continue
            ratio = used / limit
            if ratio >= self.BUDGET_WARNING_THRESHOLD:
                emitted.add(budget_type)
                await self._emit_event(
                    run_id,
                    TimelineEventType.BUDGET_WARNING,
                    agent_ctx.agent_id,
                    depth,
                    parent_ctx,
                    {
                        "budget_type": budget_type,
                        "used": used,
                        "limit": limit,
                        "ratio": round(ratio, 4),
                        "agent_id": agent_ctx.agent_id,
                    },
                )

    def _find_handoff(
        self, ir: FlowIRv2, from_agent: str, route_target: str
    ) -> HandoffRule | None:
        """Find a handoff rule matching a router's selected route."""
        for handoff in ir.get_handoffs_from(from_agent):
            if handoff.to_agent_id == route_target:
                return handoff
        return None

    async def _emit_event(
        self,
        run_id: str,
        event_type: TimelineEventType,
        agent_id: str,
        depth: int,
        parent_ctx: AgentRunContext | None,
        data: dict[str, Any],
    ) -> None:
        """Record a multi-agent timeline event."""
        event = AgentEventRecord(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            event_type=event_type,
            agent_id=agent_id,
            parent_agent_id=parent_ctx.agent_id if parent_ctx else None,
            data_json=json.dumps(data, default=str),
            timestamp=datetime.now(timezone.utc),
            depth=depth,
        )
        self.session.add(event)
        await self.session.commit()

    async def _execute_agent_step(
        self,
        run: RunRecord,
        node: Any,
        order: int,
        context: ExecutionContext,
        flow_ir: Any,
        agent_ctx: AgentRunContext,
        agent: AgentSpec,
        schema_contracts: dict[str, dict[str, Any]] | None = None,
    ) -> StepRecord:
        """Execute a step tagged with agent metadata.

        Delegates to FlowExecutor._execute_step() and then adds agent fields.
        """
        params = node.params if isinstance(node.params, dict) else {}
        retry_spec = params.get("retries")
        if isinstance(retry_spec, dict):
            retry_spec = RetrySpec.model_validate(retry_spec)
        elif retry_spec is None:
            if agent_ctx.retries is not None:
                retry_spec = agent_ctx.retries
            else:
                retry_spec = RetrySpec(
                    max_attempts=max(1, int(params.get("retry_count", 0)) + 1),
                    backoff_ms=int(float(params.get("retry_delay", 1.0)) * 1000),
                    retry_on=["timeout", "rate_limit", "5xx", "unknown"],
                    jitter=False,
                )

        async def _attempt_once(current_node: Any) -> StepRecord:
            current_params = current_node.params if isinstance(current_node.params, dict) else {}
            input_schema = self._coerce_schema_ref(current_params.get("input_schema"))
            output_schema = self._coerce_schema_ref(current_params.get("output_schema"))

            if input_schema is not None:
                tool_input_payload = {
                    "input": context.current_value,
                    "user_input": context.user_input,
                    "variables": context.variables,
                }
                soft_fail = bool(agent_ctx.policies.allow_schema_soft_fail) if agent_ctx.policies else False
                warning = validate_payload_or_raise(
                    tool_input_payload,
                    input_schema,
                    soft_fail=soft_fail,
                    schema_contracts=schema_contracts,
                )
                if warning:
                    await self._emit_event(
                        run.id,
                        TimelineEventType.SCHEMA_VALIDATION_ERROR,
                        agent_ctx.agent_id,
                        agent_ctx.depth,
                        agent_ctx.parent_run_context,
                        {"phase": "tool_input", "node_id": current_node.id, "warning": warning},
                    )

            step_local = await self._flow_executor._execute_step(
                run=run,
                node=current_node,
                order=order,
                context=context,
                flow_ir=flow_ir,
            )

            if output_schema is not None:
                payload = step_local.output_data if isinstance(step_local.output_data, dict) else {}
                soft_fail = bool(agent_ctx.policies.allow_schema_soft_fail) if agent_ctx.policies else False
                warning = validate_payload_or_raise(
                    payload,
                    output_schema,
                    soft_fail=soft_fail,
                    schema_contracts=schema_contracts,
                )
                if warning:
                    await self._emit_event(
                        run.id,
                        TimelineEventType.SCHEMA_VALIDATION_ERROR,
                        agent_ctx.agent_id,
                        agent_ctx.depth,
                        agent_ctx.parent_run_context,
                        {"phase": "tool_output", "node_id": current_node.id, "warning": warning},
                    )

            # Apply redaction policy to step payloads if needed.
            if agent_ctx.policies and agent_ctx.policies.redaction.enabled:
                if step_local.input_json:
                    step_local.input_json = apply_redaction(step_local.input_json, agent_ctx.policies)
                if step_local.output_json:
                    step_local.output_json = apply_redaction(step_local.output_json, agent_ctx.policies)
            return step_local

        async def _run_primary() -> StepRecord:
            return await _attempt_once(node)

        async def _on_retry_attempt(attempt: int, reason: str) -> None:
            await self._emit_event(
                run.id,
                TimelineEventType.RETRY_ATTEMPT,
                agent_ctx.agent_id,
                agent_ctx.depth,
                agent_ctx.parent_run_context,
                {
                    "node_id": node.id,
                    "attempt": attempt,
                    "reason": reason,
                },
            )

        try:
            step = await run_with_retry(_run_primary, retry_spec, on_attempt=_on_retry_attempt)
        except Exception as primary_exc:
            if isinstance(primary_exc, SchemaValidationError):
                await self._emit_event(
                    run.id,
                    TimelineEventType.SCHEMA_VALIDATION_ERROR,
                    agent_ctx.agent_id,
                    agent_ctx.depth,
                    agent_ctx.parent_run_context,
                    {"phase": "node_execution", "node_id": node.id, "error": str(primary_exc)},
                )
                raise

            step = None
            base_params = deepcopy(params)

            if node.type == NodeType.LLM and agent_ctx.fallbacks and agent_ctx.fallbacks.llm_chain:
                for binding in agent_ctx.fallbacks.llm_chain:
                    fallback_node = deepcopy(node)
                    fallback_node.params = {
                        **base_params,
                        "provider": binding.get("provider", base_params.get("provider")),
                        "model": binding.get("model", base_params.get("model")),
                        "temperature": binding.get("temperature", base_params.get("temperature")),
                        "system_prompt": binding.get("system_prompt", base_params.get("system_prompt")),
                    }
                    try:
                        step = await run_with_retry(
                            lambda fn_node=fallback_node: _attempt_once(fn_node),
                            retry_spec,
                            on_attempt=_on_retry_attempt,
                        )
                        await self._emit_event(
                            run.id,
                            TimelineEventType.FALLBACK_USED,
                            agent_ctx.agent_id,
                            agent_ctx.depth,
                            agent_ctx.parent_run_context,
                            {
                                "node_id": node.id,
                                "from_model": base_params.get("model"),
                                "to_model": fallback_node.params.get("model"),
                                "reason": str(primary_exc),
                            },
                        )
                        break
                    except Exception:
                        continue
            elif (
                node.type == NodeType.TOOL
                and agent_ctx.fallbacks
                and isinstance(base_params.get("tool_name"), str)
            ):
                tool_name = base_params.get("tool_name")
                tool_fallbacks = agent_ctx.fallbacks.tool_fallbacks.get(tool_name, [])
                for fallback_tool in tool_fallbacks:
                    fallback_node = deepcopy(node)
                    fallback_node.params = {
                        **base_params,
                        "tool_name": fallback_tool,
                    }
                    try:
                        step = await run_with_retry(
                            lambda fn_node=fallback_node: _attempt_once(fn_node),
                            retry_spec,
                            on_attempt=_on_retry_attempt,
                        )
                        await self._emit_event(
                            run.id,
                            TimelineEventType.FALLBACK_USED,
                            agent_ctx.agent_id,
                            agent_ctx.depth,
                            agent_ctx.parent_run_context,
                            {
                                "node_id": node.id,
                                "from_tool": tool_name,
                                "to_tool": fallback_tool,
                                "reason": str(primary_exc),
                            },
                        )
                        break
                    except Exception:
                        continue

            if step is None:
                raise primary_exc

        # Tag with agent info
        step.agent_id = agent_ctx.agent_id
        step.depth = agent_ctx.depth
        if agent_ctx.parent_run_context:
            step.parent_step_id = f"agent_{agent_ctx.parent_run_context.agent_id}"

        self.session.add(step)
        await self.session.commit()

        return step

    @staticmethod
    def _coerce_schema_ref(value: Any) -> SchemaRef | None:
        if value is None:
            return None
        if isinstance(value, SchemaRef):
            return value
        if isinstance(value, dict):
            try:
                return SchemaRef.model_validate(value)
            except Exception:
                return None
        return None
