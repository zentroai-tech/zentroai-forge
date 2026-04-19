"""Debug session API for step-by-step flow execution."""

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.models.credentials import CredentialProvider
from agent_compiler.models.ir import Flow, NodeType, parse_ir
from agent_compiler.models.ir_v2 import FlowIRv2
from agent_compiler.observability.logging import StepLogger, get_logger
from agent_compiler.runtime.context import ExecutionContext
from agent_compiler.runtime.graph_runtime import AgentGraphRuntime
from agent_compiler.runtime.node_handlers import execute_node
from agent_compiler.services.credential_service import CredentialService
from agent_compiler.services.flow_service import FlowService

logger = get_logger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])

# In-memory store for active debug sessions
# In production this would use Redis or similar, but for local dev this is fine.
_active_sessions: dict[str, "DebugSession"] = {}

# Sessions older than this are evicted on the next session creation.
SESSION_TTL_SECONDS = 30 * 60  # 30 minutes


def _gc_sessions() -> None:
    """Evict debug sessions that have exceeded SESSION_TTL_SECONDS."""
    now = time.monotonic()
    expired = [k for k, s in _active_sessions.items() if now - s.created_at > SESSION_TTL_SECONDS]
    for k in expired:
        logger.info(f"Debug session expired and evicted: {k}")
        del _active_sessions[k]


class DebugSession:
    """Represents a step-by-step debug session."""

    def __init__(
        self,
        session_id: str,
        flow_ir: AgentGraphRuntime,
        input_data: dict[str, Any],
        context: ExecutionContext,
    ):
        self.session_id = session_id
        self.flow_ir = flow_ir
        self.input_data = input_data
        self.context = context
        self.execution_order = flow_ir.get_topological_order()
        self.current_step = 0
        self.status = "paused"  # paused, running, completed, failed, aborted
        self.step_results: list[dict[str, Any]] = []
        self.error: str | None = None
        self.created_at: float = time.monotonic()
        self._resume_event = asyncio.Event()
        self._command: str = "step"  # step, continue, abort

    @property
    def current_node_id(self) -> str | None:
        if self.current_step < len(self.execution_order):
            return self.execution_order[self.current_step]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "flow_id": self.flow_ir.flow.id,
            "status": self.status,
            "current_step": self.current_step,
            "total_steps": len(self.execution_order),
            "current_node_id": self.current_node_id,
            "execution_order": self.execution_order,
            "context_snapshot": {
                "user_input": self.context.user_input,
                "variables": self.context.variables,
                "node_outputs": self.context.node_outputs,
                "retrieved_docs_count": len(self.context.retrieved_docs),
            },
            "step_results": self.step_results,
            "error": self.error,
        }


class DebugStartRequest(BaseModel):
    """Request to start a debug session."""

    input: dict[str, Any] = Field(default_factory=dict)
    entrypoint: str = Field(default="main")
    agent_id: str | None = Field(default=None)


class DebugCommandRequest(BaseModel):
    """Command for an active debug session."""

    command: str = Field(
        ...,
        description="step (next node), continue (run all remaining), abort (stop)",
    )
    variable_overrides: dict[str, Any] | None = Field(
        default=None,
        description="Override context variables before the next step",
    )


@router.post("/flows/{flow_id}/start")
async def start_debug_session(
    flow_id: str,
    req: DebugStartRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start a new step-by-step debug session for a flow.

    Returns the session ID and initial state (paused at step 0).
    """
    flow_service = FlowService(session)
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    parsed_ir = parse_ir(json.loads(flow.ir_json))
    if not isinstance(parsed_ir, FlowIRv2):
        raise HTTPException(status_code=400, detail="Only ir_version='2' is supported")
    flow_ir = _build_debug_ir(parsed_ir, req.entrypoint, req.agent_id)
    session_id = f"dbg_{uuid.uuid4().hex[:12]}"

    # Resolve credentials
    cred_service = CredentialService(session)
    credentials: dict[str, str] = {}
    for provider in CredentialProvider:
        try:
            key = await cred_service.resolve_credential(
                provider=provider,
                project_id=flow_id,
                allow_env_fallback=True,
            )
            credentials[provider.value] = key
        except Exception:
            pass

    context = ExecutionContext(
        user_input=req.input,
        resolved_credentials=credentials,
    )

    # Evict expired sessions before adding a new one (lazy GC)
    _gc_sessions()

    debug_session = DebugSession(
        session_id=session_id,
        flow_ir=flow_ir,
        input_data=req.input,
        context=context,
    )
    _active_sessions[session_id] = debug_session

    logger.info(f"Debug session started: {session_id} for flow {flow_id}")
    return debug_session.to_dict()


@router.post("/sessions/{session_id}/command")
async def send_debug_command(
    session_id: str,
    req: DebugCommandRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Execute the next step(s) in a debug session.

    Commands:
    - step: Execute only the next node, then pause
    - continue: Execute all remaining nodes without pausing
    - abort: Stop the session immediately
    """
    debug_session = _active_sessions.get(session_id)
    if debug_session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")

    if debug_session.status in ("completed", "failed", "aborted"):
        return debug_session.to_dict()

    # Apply variable overrides if provided
    if req.variable_overrides:
        debug_session.context.variables.update(req.variable_overrides)

    command = req.command.lower()

    if command == "abort":
        debug_session.status = "aborted"
        _cleanup_session(session_id)
        return debug_session.to_dict()

    # Determine how many steps to run
    run_all = command == "continue"
    flow_ir = debug_session.flow_ir

    while debug_session.current_step < len(debug_session.execution_order):
        node_id = debug_session.execution_order[debug_session.current_step]
        node = flow_ir.get_node(node_id)
        if node is None:
            debug_session.status = "failed"
            debug_session.error = f"Node not found: {node_id}"
            break

        debug_session.status = "running"

        # Create a temporary StepLogger
        step_logger = StepLogger(
            run_id=session_id,
            step_id=f"{session_id}_step_{debug_session.current_step}",
            node_id=node.id,
            node_type=node.type.value,
        )

        try:
            output = await execute_node(
                node=node,
                context=debug_session.context,
                flow_engine=flow_ir.flow.engine_preference,
                logger=step_logger,
            )
            debug_session.context.set_node_output(node.id, output)

            # Handle router
            if node.type == NodeType.ROUTER:
                selected_route = output.get("selected_route")
                if selected_route:
                    debug_session.context.variables["_next_node"] = selected_route

            debug_session.step_results.append({
                "step": debug_session.current_step,
                "node_id": node.id,
                "node_type": node.type.value,
                "status": "completed",
                "output": output,
            })

        except Exception as e:
            debug_session.step_results.append({
                "step": debug_session.current_step,
                "node_id": node.id,
                "node_type": node.type.value,
                "status": "failed",
                "error": str(e),
            })
            debug_session.status = "failed"
            debug_session.error = str(e)
            break

        debug_session.current_step += 1

        # If "step" mode, pause after one step
        if not run_all:
            debug_session.status = "paused"
            break

    # Check if we finished all steps
    if debug_session.current_step >= len(debug_session.execution_order) and debug_session.status != "failed":
        debug_session.status = "completed"
        _cleanup_session(session_id, delay=120)

    return debug_session.to_dict()


@router.get("/sessions/{session_id}")
async def get_debug_session(session_id: str) -> dict[str, Any]:
    """Get the current state of a debug session."""
    debug_session = _active_sessions.get(session_id)
    if debug_session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")
    return debug_session.to_dict()


@router.delete("/sessions/{session_id}")
async def delete_debug_session(session_id: str):
    """Delete/abort a debug session."""
    debug_session = _active_sessions.pop(session_id, None)
    if debug_session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")
    debug_session.status = "aborted"
    return {"status": "deleted"}


# ── Prompt Playground: test a single node ────────────────────────────


class PromptTestRequest(BaseModel):
    """Request to test a single LLM node with variable overrides."""

    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Template variables to inject (e.g. {input}, {context})",
    )
    model_override: str | None = Field(
        default=None,
        description="Override the model for this test",
    )
    temperature_override: float | None = Field(
        default=None,
        description="Override temperature",
    )
    entrypoint: str = Field(default="main")
    agent_id: str | None = Field(default=None)


def _build_debug_ir(
    flow_ir: FlowIRv2,
    entrypoint: str = "main",
    agent_id: str | None = None,
) -> AgentGraphRuntime:
    """Build a temporary single-agent runtime graph for debug execution."""
    resolved_agent_id = agent_id
    if resolved_agent_id is None:
        ep = flow_ir.get_entrypoint(entrypoint)
        if ep is None:
            raise ValueError(f"Entrypoint '{entrypoint}' not found")
        resolved_agent_id = ep.agent_id

    agent = flow_ir.get_agent(resolved_agent_id)
    if agent is None:
        raise ValueError(f"Agent '{resolved_agent_id}' not found")

    return AgentGraphRuntime(
        flow=Flow(
            id=f"{flow_ir.flow.id}__debug__{agent.id}",
            name=f"{flow_ir.flow.name} / {agent.name}",
            version=flow_ir.flow.version,
            engine_preference=flow_ir.flow.engine_preference,
            description=flow_ir.flow.description,
        ),
        nodes=agent.graph.nodes,
        edges=agent.graph.edges,
    )


@router.post("/flows/{flow_id}/nodes/{node_id}/test")
async def test_node(
    flow_id: str,
    node_id: str,
    req: PromptTestRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Test a single LLM node with custom variables.

    Renders the prompt template with provided variables, then executes only
    that node. Useful for prompt iteration without running the entire flow.
    """
    flow_service = FlowService(session)
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    parsed_ir = parse_ir(json.loads(flow.ir_json))
    if not isinstance(parsed_ir, FlowIRv2):
        raise HTTPException(status_code=400, detail="Only ir_version='2' is supported")
    flow_ir = _build_debug_ir(parsed_ir, req.entrypoint, req.agent_id)
    node = flow_ir.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    if node.type != NodeType.LLM:
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is type {node.type.value}, not LLM",
        )

    # Apply model/temperature overrides
    from agent_compiler.models.ir import LLMParams

    params = LLMParams.model_validate(node.params)
    if req.model_override:
        params.model = req.model_override
    if req.temperature_override is not None:
        params.temperature = req.temperature_override

    # Build context with user-supplied variables
    context = ExecutionContext(user_input=req.variables)
    # Also set each variable directly so template rendering can use them
    for k, v in req.variables.items():
        context.variables[k] = v
    # Set current_value to "input" if it exists for convenience
    if "input" in req.variables:
        context.variables["current_value"] = req.variables["input"]

    # Resolve credentials
    cred_service = CredentialService(session)
    credentials: dict[str, str] = {}
    for provider in CredentialProvider:
        try:
            key = await cred_service.resolve_credential(
                provider=provider,
                project_id=flow_id,
                allow_env_fallback=True,
            )
            credentials[provider.value] = key
        except Exception:
            pass
    context.resolved_credentials = credentials

    # Render the prompt to show the user
    rendered_prompt = context.render_template(params.prompt_template)
    rendered_system = context.render_template(params.system_prompt) if params.system_prompt else None

    # Execute the node
    step_logger = StepLogger("prompt_test", "prompt_test_step", node_id, "LLM")
    try:
        # Temporarily update node params for execution
        original_params = node.params
        node.params = params.model_dump()

        output = await execute_node(
            node=node,
            context=context,
            flow_engine=flow_ir.flow.engine_preference,
            logger=step_logger,
        )
        node.params = original_params  # restore

        return {
            "node_id": node_id,
            "model": params.model,
            "temperature": params.temperature,
            "rendered_prompt": rendered_prompt,
            "rendered_system_prompt": rendered_system,
            "output": output,
            "status": "success",
        }
    except Exception as e:
        return {
            "node_id": node_id,
            "model": params.model,
            "temperature": params.temperature,
            "rendered_prompt": rendered_prompt,
            "rendered_system_prompt": rendered_system,
            "output": None,
            "error": str(e),
            "status": "failed",
        }


def _cleanup_session(session_id: str, delay: int = 0):
    """Remove session from memory after optional delay."""
    if delay <= 0:
        _active_sessions.pop(session_id, None)
    else:
        async def _delayed():
            await asyncio.sleep(delay)
            _active_sessions.pop(session_id, None)

        asyncio.ensure_future(_delayed())
