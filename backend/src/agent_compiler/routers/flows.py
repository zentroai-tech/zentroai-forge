"""Flow management API endpoints."""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.models.ir import parse_ir
from agent_compiler.services.encryption_service import (
    encrypt_secret,
    is_encryption_configured,
    EncryptionError,
)
from agent_compiler.services.export_service import ExportService, ExportTarget
from agent_compiler.services.export_config import (
    ExportConfig,
    ExportEngine,
    ExportSurface,
    ExportPackaging,
    VALID_PRESETS,
)
from agent_compiler.services.flow_service import FlowService
from agent_compiler.services.run_service import RunService

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["flows"])


class FlowCreate(BaseModel):
    """Request body for creating a flow.

    Accepts v2 (ir_version "2") IR format only.
    """

    ir_version: str = Field(default="2", pattern=r"^2$")
    flow: dict[str, Any]
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    # v2 fields
    agents: list[dict[str, Any]] = Field(default_factory=list)
    entrypoints: list[dict[str, Any]] = Field(default_factory=list)
    handoffs: list[dict[str, Any]] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict)
    policies: dict[str, Any] = Field(default_factory=dict)


class FlowResponse(BaseModel):
    """Response body for flow operations."""

    id: str
    name: str
    version: str
    description: str
    engine_preference: str
    created_at: str
    updated_at: str


class FlowDetailResponse(FlowResponse):
    """Detailed flow response including IR."""

    ir: dict[str, Any]


class RunCreate(BaseModel):
    """Request body for creating a run."""

    input: dict[str, Any] = Field(default_factory=dict)
    entrypoint: str | None = Field(
        default=None,
        description="Entrypoint name for v2 multi-agent flows (default: 'main')",
    )


class RunResponse(BaseModel):
    """Response body for run operations."""

    id: str
    flow_id: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


def _flow_to_response(flow) -> FlowResponse:
    """Convert a flow record to response model."""
    return FlowResponse(
        id=flow.id,
        name=flow.name,
        version=flow.version,
        description=flow.description,
        engine_preference=flow.engine_preference,
        created_at=flow.created_at.isoformat(),
        updated_at=flow.updated_at.isoformat(),
    )


def _flow_to_detail_response(flow) -> FlowDetailResponse:
    """Convert a flow record to detailed response model."""
    return FlowDetailResponse(
        id=flow.id,
        name=flow.name,
        version=flow.version,
        description=flow.description,
        engine_preference=flow.engine_preference,
        created_at=flow.created_at.isoformat(),
        updated_at=flow.updated_at.isoformat(),
        ir=json.loads(flow.ir_json),
    )


@router.post("", response_model=FlowResponse, status_code=201)
async def create_flow(
    flow_data: FlowCreate,
    session: AsyncSession = Depends(get_session),
) -> FlowResponse:
    """Create a new flow from IR data."""
    service = FlowService(session)

    try:
        if flow_data.ir_version != "2":
            raise ValueError("Only ir_version='2' is supported.")
        flow = await service.create_flow(flow_data.model_dump())
        return _flow_to_response(flow)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[FlowResponse])
async def list_flows(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[FlowResponse]:
    """List all flows with pagination."""
    service = FlowService(session)
    flows = await service.list_flows(limit=limit, offset=offset)
    return [_flow_to_response(f) for f in flows]


@router.get("/{flow_id}", response_model=FlowDetailResponse)
async def get_flow(
    flow_id: str,
    session: AsyncSession = Depends(get_session),
) -> FlowDetailResponse:
    """Get a flow by ID."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)

    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    return _flow_to_detail_response(flow)


@router.put("/{flow_id}", response_model=FlowResponse)
async def update_flow(
    flow_id: str,
    flow_data: FlowCreate,
    session: AsyncSession = Depends(get_session),
) -> FlowResponse:
    """Update an existing flow."""
    service = FlowService(session)

    try:
        if flow_data.ir_version != "2":
            raise ValueError("Only ir_version='2' is supported.")
        flow = await service.update_flow(flow_id, flow_data.model_dump())
        return _flow_to_response(flow)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(
    flow_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a flow."""
    service = FlowService(session)
    deleted = await service.delete_flow(flow_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")


# ── Version History ──────────────────────────────────────────────────


@router.get("/{flow_id}/versions")
async def list_flow_versions(
    flow_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List all versions for a flow, newest first."""
    service = FlowService(session)
    flow = await service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    versions = await service.list_versions(flow_id, limit=limit)
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "label": v.label,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]


@router.get("/{flow_id}/versions/{version_number}")
async def get_flow_version(
    flow_id: str,
    version_number: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific version with full IR."""
    service = FlowService(session)
    version = await service.get_version(flow_id, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found")

    return {
        "id": version.id,
        "version_number": version.version_number,
        "label": version.label,
        "created_at": version.created_at.isoformat(),
        "ir": json.loads(version.ir_json),
    }


class RestoreVersionRequest(BaseModel):
    """Request to restore a specific version."""
    version_number: int


@router.post("/{flow_id}/versions/restore")
async def restore_flow_version(
    flow_id: str,
    req: RestoreVersionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Restore a flow to a specific version."""
    service = FlowService(session)
    try:
        flow = await service.restore_version(flow_id, req.version_number)
        return _flow_to_response(flow)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class LabelVersionRequest(BaseModel):
    """Request to label a version."""
    label: str


@router.patch("/{flow_id}/versions/{version_number}")
async def label_flow_version(
    flow_id: str,
    version_number: int,
    req: LabelVersionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add/update a label on a version."""
    service = FlowService(session)
    try:
        v = await service.label_version(flow_id, version_number, req.label)
        return {
            "id": v.id,
            "version_number": v.version_number,
            "label": v.label,
            "created_at": v.created_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Environment Variables / Profiles ─────────────────────────────────


class EnvVarCreate(BaseModel):
    """Request to create/update an env var."""
    key: str
    value: str
    profile: str = "development"
    is_secret: bool = False


class EnvVarResponse(BaseModel):
    """Response for an env var."""
    id: str
    key: str
    value: str
    profile: str
    is_secret: bool
    created_at: str


@router.get("/{flow_id}/env")
async def list_env_vars(
    flow_id: str,
    profile: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List environment variables for a flow, optionally filtered by profile."""
    from sqlmodel import select
    from agent_compiler.models.db import FlowEnvVar

    stmt = select(FlowEnvVar).where(FlowEnvVar.flow_id == flow_id)
    if profile:
        stmt = stmt.where(FlowEnvVar.profile == profile)
    stmt = stmt.order_by(FlowEnvVar.profile, FlowEnvVar.key)

    result = await session.execute(stmt)
    env_vars = list(result.scalars().all())

    return [
        {
            "id": v.id,
            "key": v.key,
            "value": "***" if v.is_secret else v.value,
            "profile": v.profile,
            "is_secret": v.is_secret,
            "created_at": v.created_at.isoformat(),
        }
        for v in env_vars
    ]


@router.post("/{flow_id}/env")
async def create_env_var(
    flow_id: str,
    req: EnvVarCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create or update an environment variable for a flow."""
    import uuid as _uuid
    from sqlmodel import select
    from agent_compiler.models.db import FlowEnvVar
    from datetime import datetime, timezone

    flow_service = FlowService(session)
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    # Check if it already exists (upsert)
    stmt = select(FlowEnvVar).where(
        FlowEnvVar.flow_id == flow_id,
        FlowEnvVar.profile == req.profile,
        FlowEnvVar.key == req.key,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    # Encrypt secret values when encryption is configured
    store_value = req.value
    if req.is_secret and store_value and is_encryption_configured():
        try:
            store_value = encrypt_secret(store_value)
        except EncryptionError:
            _logger.warning("Encryption failed for env var %s; storing as plaintext", req.key)

    if existing:
        existing.value = store_value
        existing.is_secret = req.is_secret
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        var = existing
    else:
        var = FlowEnvVar(
            id=f"env_{_uuid.uuid4().hex[:12]}",
            flow_id=flow_id,
            profile=req.profile,
            key=req.key,
            value=store_value,
            is_secret=req.is_secret,
        )
        session.add(var)
        await session.commit()
        await session.refresh(var)

    return {
        "id": var.id,
        "key": var.key,
        "value": "***" if var.is_secret else var.value,
        "profile": var.profile,
        "is_secret": var.is_secret,
        "created_at": var.created_at.isoformat(),
    }


@router.delete("/{flow_id}/env/{var_id}", status_code=204)
async def delete_env_var(
    flow_id: str,
    var_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an environment variable."""
    from sqlmodel import select
    from agent_compiler.models.db import FlowEnvVar

    stmt = select(FlowEnvVar).where(
        FlowEnvVar.id == var_id,
        FlowEnvVar.flow_id == flow_id,
    )
    result = await session.execute(stmt)
    var = result.scalar_one_or_none()
    if var is None:
        raise HTTPException(status_code=404, detail="Variable not found")

    await session.delete(var)
    await session.commit()


@router.get("/{flow_id}/env/profiles")
async def list_profiles(
    flow_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """List all environment profiles defined for a flow."""
    from sqlmodel import select
    from agent_compiler.models.db import FlowEnvVar

    stmt = (
        select(FlowEnvVar.profile)
        .where(FlowEnvVar.flow_id == flow_id)
        .distinct()
    )
    result = await session.execute(stmt)
    profiles = [row[0] for row in result.fetchall()]
    # Always include defaults
    for p in ("development", "staging", "production"):
        if p not in profiles:
            profiles.append(p)
    return sorted(profiles)


@router.post("/{flow_id}/runs", response_model=dict[str, Any], status_code=201)
async def create_run(
    flow_id: str,
    run_data: RunCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create and execute a new run for a flow."""
    flow_service = FlowService(session)
    run_service = RunService(session)

    # Get the flow
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    try:
        # Execute the run
        run = await run_service.create_run(
            flow,
            run_data.input,
            entrypoint=run_data.entrypoint,
        )

        # Return detailed run info
        run_detail = await run_service.get_run_with_steps(run.id)
        return run_detail
    except Exception:
        _logger.error("Run execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error. Check server logs.")


@router.post("/{flow_id}/runs/stream")
async def stream_run(
    flow_id: str,
    run_data: RunCreate,
    session: AsyncSession = Depends(get_session),
):
    """Stream a flow execution via Server-Sent Events (SSE).

    Events emitted:
    - step_started: {run_id, node_id, node_type, order}
    - step_completed: {run_id, node_id, node_type, order, output, duration_ms}
    - step_failed: {run_id, error}
    - run_completed: {run_id, status}
    - run_failed: {run_id, status, error}
    """
    from agent_compiler.runtime.executor import FlowExecutor

    flow_service = FlowService(session)
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    try:
        flow_ir = parse_ir(json.loads(flow.ir_json))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    executor = FlowExecutor(session)
    event_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def on_event(event_type: str, payload: dict[str, Any]):
        data = json.dumps({"type": event_type, **payload}, default=str)
        await event_queue.put(f"event: {event_type}\ndata: {data}\n\n")

    async def run_flow():
        try:
            run = await executor.execute_streaming(
                flow_ir,
                run_data.input,
                on_event=on_event,
                entrypoint=run_data.entrypoint,
            )
            # Send final detail
            run_service = RunService(session)
            detail = await run_service.get_run_with_steps(run.id)
            final = json.dumps({"type": "run_detail", "detail": detail}, default=str)
            await event_queue.put(f"event: run_detail\ndata: {final}\n\n")
        except Exception as e:
            err = json.dumps({"type": "error", "error": str(e)})
            await event_queue.put(f"event: error\ndata: {err}\n\n")
        finally:
            await event_queue.put(None)  # sentinel

    async def event_generator():
        task = asyncio.create_task(run_flow())
        while True:
            msg = await event_queue.get()
            if msg is None:
                break
            yield msg
        await task  # ensure cleanup

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{flow_id}/runs", response_model=list[RunResponse])
async def list_runs(
    flow_id: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[RunResponse]:
    """List runs for a flow."""
    flow_service = FlowService(session)
    run_service = RunService(session)

    # Verify flow exists
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    runs = await run_service.list_runs(flow_id, limit=limit, offset=offset)

    return [
        RunResponse(
            id=r.id,
            flow_id=r.flow_id,
            status=r.status.value,
            created_at=r.created_at.isoformat(),
            started_at=r.started_at.isoformat() if r.started_at else None,
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
        )
        for r in runs
    ]


class DeleteRunsResponse(BaseModel):
    """Response body for bulk run deletion."""

    deleted: int


@router.delete("/{flow_id}/runs", response_model=DeleteRunsResponse)
async def delete_all_runs(
    flow_id: str,
    session: AsyncSession = Depends(get_session),
) -> DeleteRunsResponse:
    """Delete all runs for a flow."""
    flow_service = FlowService(session)
    run_service = RunService(session)

    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    count = await run_service.delete_all_runs(flow_id)
    return DeleteRunsResponse(deleted=count)


# ── Chat Playground ──────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str = Field(..., min_length=1)
    conversation_id: str | None = Field(
        default=None,
        description="ID to group messages into a conversation. Omit to start a new one.",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Previous messages for multi-turn context.",
    )


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    response: str
    conversation_id: str
    run_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/{flow_id}/chat", response_model=ChatResponse)
async def chat_with_flow(
    flow_id: str,
    chat_req: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Chat with a flow — sends a message and returns the agent's text response.

    This is a convenience wrapper around the run system designed for
    conversational testing. It:
    1. Builds an input payload with the user message + conversation history
    2. Executes the flow
    3. Extracts the output text from the Output node (or last node)
    4. Returns a clean response with optional metadata

    Multi-turn: pass ``conversation_id`` and ``history`` to maintain context.
    """
    import uuid

    flow_service = FlowService(session)
    run_service = RunService(session)

    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    conversation_id = chat_req.conversation_id or uuid.uuid4().hex[:12]

    # Build input with conversation context
    input_data: dict[str, Any] = {"input": chat_req.message}
    if chat_req.history:
        input_data["history"] = [
            {"role": m.role, "content": m.content} for m in chat_req.history
        ]
        input_data["conversation_id"] = conversation_id

    try:
        run = await run_service.create_run(flow, input_data)
        run_detail = await run_service.get_run_with_steps(run.id)
    except Exception:
        _logger.error("Chat run execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error. Check server logs.")

    # Extract the text response from the last completed step (Output node preferred)
    def _extract_text(raw: Any) -> str:
        """Pull a clean string from a node output value.

        The value may be a plain string, or a nested dict (e.g. a
        stringified LLM output dict that was later parsed as JSON).
        """
        if isinstance(raw, dict):
            # Prefer the inner "output" key (LLM / Output node structure)
            return str(raw.get("output", raw))
        return str(raw)

    response_text = ""
    steps = run_detail.get("timeline", []) if run_detail else []
    for step in reversed(steps):
        output = step.get("output") or {}
        if step.get("node_type") == "Output" and output.get("output"):
            response_text = _extract_text(output["output"])
            break
        if output.get("output") and not response_text:
            response_text = _extract_text(output["output"])

    if not response_text and run_detail and run_detail.get("error_message"):
        response_text = f"Error: {run_detail['error_message']}"

    # Build metadata
    metadata: dict[str, Any] = {
        "status": run_detail.get("status", "unknown") if run_detail else "failed",
        "duration_ms": run_detail.get("duration_ms") if run_detail else None,
        "steps": len(steps),
    }
    # Collect model info from LLM steps
    for step in steps:
        if step.get("node_type") == "LLM" and step.get("output"):
            out = step["output"]
            if out.get("model"):
                metadata.setdefault("models_used", []).append(out["model"])
            if out.get("tokens_used"):
                metadata["tokens_used"] = metadata.get("tokens_used", 0) + (out["tokens_used"] or 0)

    return ChatResponse(
        response=response_text or "(no output)",
        conversation_id=conversation_id,
        run_id=run_detail["id"] if run_detail else "",
        metadata=metadata,
    )


# ── Batch Run ────────────────────────────────────────────────────────


class BatchRunRequest(BaseModel):
    """Request body for batch run."""

    inputs: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Array of input payloads to execute sequentially",
    )


class BatchRunResultItem(BaseModel):
    """Result for a single input in a batch run."""

    index: int
    run_id: str
    status: str
    output: str | None = None
    error: str | None = None
    duration_ms: float | None = None
    tokens_total: int | None = None


class BatchRunResponse(BaseModel):
    """Response for batch run."""

    flow_id: str
    total: int
    completed: int
    failed: int
    results: list[BatchRunResultItem]


@router.post("/{flow_id}/batch", response_model=BatchRunResponse)
async def batch_run_flow(
    flow_id: str,
    batch_req: BatchRunRequest,
    session: AsyncSession = Depends(get_session),
) -> BatchRunResponse:
    """Execute a flow with multiple inputs sequentially and return all results."""
    flow_service = FlowService(session)
    run_service = RunService(session)

    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    results: list[BatchRunResultItem] = []
    completed = 0
    failed = 0

    for idx, input_data in enumerate(batch_req.inputs):
        try:
            run = await run_service.create_run(flow, input_data)
            run_detail = await run_service.get_run_with_steps(run.id)

            # Extract output text from Output node
            output_text = None
            tokens_total = 0
            if run_detail:
                for step in reversed(run_detail.get("timeline", [])):
                    output = step.get("output") or {}
                    if step.get("node_type") == "Output" and output.get("output"):
                        output_text = str(output["output"])
                        break
                    if output.get("output") and not output_text:
                        output_text = str(output["output"])
                    # Sum tokens
                    if step.get("tokens") and step["tokens"].get("total"):
                        tokens_total += step["tokens"]["total"]

            duration = run_detail.get("duration_ms") if run_detail else None
            status = run_detail.get("status", "unknown") if run_detail else "failed"

            results.append(BatchRunResultItem(
                index=idx,
                run_id=run.id,
                status=status,
                output=output_text,
                duration_ms=duration,
                tokens_total=tokens_total or None,
            ))
            if status == "completed":
                completed += 1
            else:
                failed += 1

        except Exception as e:
            results.append(BatchRunResultItem(
                index=idx,
                run_id="",
                status="failed",
                error=str(e),
            ))
            failed += 1

    return BatchRunResponse(
        flow_id=flow_id,
        total=len(batch_req.inputs),
        completed=completed,
        failed=failed,
        results=results,
    )


# ── Cost Summary ─────────────────────────────────────────────────────

# Approximate price per 1M tokens (input / output) for common models.
# This is used for cost estimation only — real billing varies.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    # Google Gemini
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    # Anthropic
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-3.5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
}


def _estimate_cost(model: str | None, tokens_input: int, tokens_output: int, tokens_total: int) -> float:
    """Estimate cost in USD for a given model and token counts."""
    if not model:
        return 0.0
    # Try exact match first, then prefix match
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        for prefix, p in MODEL_PRICING.items():
            if model.startswith(prefix):
                pricing = p
                break
    if not pricing:
        return 0.0
    input_cost = (tokens_input / 1_000_000) * pricing[0]
    output_cost = (tokens_output / 1_000_000) * pricing[1]
    return round(input_cost + output_cost, 6)


@router.get("/{flow_id}/costs")
async def get_flow_costs(
    flow_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get token usage and estimated cost summary for recent runs of a flow."""
    from sqlmodel import select
    from agent_compiler.models.db import StepRecord, RunRecord

    flow_service = FlowService(session)
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    run_service = RunService(session)
    runs = await run_service.list_runs(flow_id, limit=limit)

    run_costs = []
    total_tokens = 0
    total_cost = 0.0

    for run in runs:
        steps = await run_service.get_run_steps(run.id)
        run_tokens = 0
        run_cost = 0.0
        step_details = []

        for step in steps:
            t_in = getattr(step, "tokens_input", None) or 0
            t_out = getattr(step, "tokens_output", None) or 0
            t_total = getattr(step, "tokens_total", None) or 0
            model = getattr(step, "model_name", None)

            if t_total > 0:
                cost = _estimate_cost(model, t_in, t_out, t_total)
                run_tokens += t_total
                run_cost += cost
                step_details.append({
                    "node_id": step.node_id,
                    "model": model,
                    "tokens_input": t_in,
                    "tokens_output": t_out,
                    "tokens_total": t_total,
                    "estimated_cost_usd": cost,
                })

        total_tokens += run_tokens
        total_cost += run_cost

        if step_details:
            duration_ms = None
            if run.started_at and run.finished_at:
                duration_ms = (run.finished_at - run.started_at).total_seconds() * 1000

            run_costs.append({
                "run_id": run.id,
                "status": run.status.value,
                "created_at": run.created_at.isoformat(),
                "duration_ms": duration_ms,
                "tokens_total": run_tokens,
                "estimated_cost_usd": round(run_cost, 6),
                "steps": step_details,
            })

    return {
        "flow_id": flow_id,
        "total_runs_analyzed": len(runs),
        "total_tokens": total_tokens,
        "total_estimated_cost_usd": round(total_cost, 6),
        "runs": run_costs,
        "pricing_table": {k: {"input_per_1m": v[0], "output_per_1m": v[1]} for k, v in MODEL_PRICING.items()},
    }


class ExportRequest(BaseModel):
    """Request body for export operations.

    Supports two calling conventions:

    **Preset (legacy / simple)**::

        {"target": "langgraph"}        # or "runtime", "api_server", "aws-ecs"

    **Composition (advanced)**::

        {"engine": "langgraph", "surface": "http", "packaging": "aws-ecs"}

    When both are provided the composition fields take priority.
    """

    # Legacy preset field
    target: str | None = Field(
        default=None,
        description="Preset name: 'langgraph', 'runtime', 'api_server', 'aws-ecs'",
    )
    # Composable fields (advanced)
    engine: str | None = Field(
        default=None,
        description="Engine: 'dispatcher' (default) or 'langgraph'",
    )
    surface: str | None = Field(
        default=None,
        description="Surface: 'cli' (default) or 'http'",
    )
    packaging: str | None = Field(
        default=None,
        description="Packaging: 'local' (default) or 'aws-ecs'",
    )
    include_tests: bool = Field(
        default=True,
        description="Whether to include test files in the export",
    )

    def to_export_config(self) -> ExportConfig:
        """Resolve this request to an ExportConfig.

        Composition fields (engine/surface/packaging) take priority over
        the legacy ``target`` preset when any are provided.
        """
        if self.engine is not None or self.surface is not None or self.packaging is not None:
            # Advanced composition path
            try:
                engine = ExportEngine(self.engine or "dispatcher")
            except ValueError:
                raise ValueError(f"Invalid engine: {self.engine!r}. Valid: {[e.value for e in ExportEngine]}")
            try:
                surface = ExportSurface(self.surface or "cli")
            except ValueError:
                raise ValueError(f"Invalid surface: {self.surface!r}. Valid: {[s.value for s in ExportSurface]}")
            try:
                packaging = ExportPackaging(self.packaging or "local")
            except ValueError:
                raise ValueError(f"Invalid packaging: {self.packaging!r}. Valid: {[p.value for p in ExportPackaging]}")
            cfg = ExportConfig(engine=engine, surface=surface, packaging=packaging)
        else:
            # Legacy preset path
            preset = (self.target or "langgraph").lower()
            if preset not in VALID_PRESETS:
                raise ValueError(
                    f"Invalid export target: {preset!r}. "
                    f"Valid presets: {VALID_PRESETS}"
                )
            cfg = ExportConfig.from_preset(preset)

        cfg.validate_composition()
        return cfg


class ExportResponse(BaseModel):
    """Response body for export operations."""

    export_id: str
    flow_id: str
    status: str
    target: str
    download_url: str
    manifest_url: str


@router.post("/{flow_id}/export", response_model=ExportResponse)
async def export_flow(
    flow_id: str,
    export_request: ExportRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> ExportResponse:
    """Export a flow as a Python project.

    Accepts optional JSON body:
    - target: "langgraph" (default) or "runtime"
    - include_tests: true (default) or false

    Creates a persistent export that can be:
    - Downloaded as a ZIP file via download_url
    - Previewed via the manifest_url

    Returns export info with URLs for accessing the export.
    """
    from agent_compiler.services.preview_service import PreviewService

    # Default export options
    if export_request is None:
        export_request = ExportRequest()

    # Resolve to a composable ExportConfig (validates combination)
    try:
        export_config = export_request.to_export_config()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    flow_service = FlowService(session)
    export_service = ExportService()
    preview_service = PreviewService(session)

    # Get the flow
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    # Parse IR
    flow_ir = flow_service.get_flow_ir(flow)

    # Generate persistent export
    export_dir, zip_path = export_service.export_flow_persistent(
        flow_ir,
        config=export_config,
        include_tests=export_request.include_tests,
    )

    # Create export record (store cache_key as the target label for display)
    export = await preview_service.create_export(
        flow_id=flow_id,
        export_dir=export_dir,
        zip_path=zip_path,
        target=export_config.cache_key,
    )

    return ExportResponse(
        export_id=export.id,
        flow_id=flow_id,
        status=export.status.value,
        target=export_config.cache_key,
        download_url=f"/exports/{export.id}/download",
        manifest_url=f"/exports/{export.id}/manifest",
    )


@router.get("/{flow_id}/exports", response_model=list[ExportResponse])
async def list_flow_exports(
    flow_id: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
) -> list[ExportResponse]:
    """List recent exports for a flow."""
    from agent_compiler.services.preview_service import PreviewService

    flow_service = FlowService(session)
    preview_service = PreviewService(session)

    # Verify flow exists
    flow = await flow_service.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    exports = await preview_service.list_exports_for_flow(flow_id, limit=limit)

    return [
        ExportResponse(
            export_id=e.id,
            flow_id=e.flow_id,
            status=e.status.value,
            target=e.target or "langgraph",
            download_url=f"/exports/{e.id}/download",
            manifest_url=f"/exports/{e.id}/manifest",
        )
        for e in exports
    ]
