"""Run management API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.models.db import ReplayConfig, ReplayMode
from agent_compiler.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])
_logger = logging.getLogger(__name__)


class ReplayRequest(BaseModel):
    """Request body for deterministic replay."""

    mode: str = Field(
        default="exact",
        description="Replay mode: 'exact' (mock all), 'mock_tools' (re-run LLMs), 'mock_all'",
    )
    mock_overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Override specific node outputs by node_id",
    )
    skip_nodes: list[str] = Field(
        default_factory=list,
        description="Node IDs to skip during replay",
    )


class ArtifactsResponse(BaseModel):
    """Response for run artifacts."""

    run_id: str
    artifacts: dict[str, list[dict[str, Any]]]


@router.get("/{run_id}", response_model=dict[str, Any])
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get detailed run information including timeline."""
    service = RunService(session)
    run_detail = await service.get_run_with_steps(run_id)

    if run_detail is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    return run_detail


@router.delete("/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a specific run and its steps."""
    service = RunService(session)
    deleted = await service.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


@router.post("/{run_id}/replay", response_model=dict[str, Any])
async def replay_run(
    run_id: str,
    replay_request: ReplayRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Replay a run using its stored IR snapshot and artifacts.

    **Replay Modes:**
    - `exact`: Replay with all external calls mocked (default). Uses stored outputs.
    - `mock_tools`: Re-run LLM calls but mock tool executions.
    - `mock_all`: Mock all external calls (LLMs, tools, retrievers).

    **Mock Overrides:**
    Override specific node outputs to test different scenarios:
    ```json
    {
        "mode": "exact",
        "mock_overrides": {
            "retriever_1": {"documents": [{"content": "Custom doc", "source": "test"}]}
        }
    }
    ```

    **Skip Nodes:**
    Skip specific nodes during replay:
    ```json
    {
        "mode": "exact",
        "skip_nodes": ["output_1"]
    }
    ```
    """
    from agent_compiler.services.replay_service import ReplayService

    # Parse replay config
    config = None
    if replay_request:
        try:
            mode = ReplayMode(replay_request.mode)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid replay mode: {replay_request.mode}. "
                f"Must be one of: exact, mock_tools, mock_all",
            )

        config = ReplayConfig(
            mode=mode,
            mock_overrides=replay_request.mock_overrides,
            skip_nodes=replay_request.skip_nodes,
        )

    service = RunService(session)
    replay_service = ReplayService(session)

    try:
        new_run = await replay_service.replay_run(run_id, config)
        run_detail = await service.get_run_with_steps(new_run.id)
        return run_detail
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        _logger.error("Replay execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error. Check server logs.")


@router.get("/{run_id}/artifacts", response_model=ArtifactsResponse)
async def get_run_artifacts(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> ArtifactsResponse:
    """Get all artifacts captured during a run.

    Artifacts include:
    - LLM responses with model info and token counts
    - Tool outputs
    - Retrieval results with documents and scores
    - Router decisions

    Useful for:
    - Debugging run behavior
    - Building mock contexts for replay
    - Analyzing LLM interactions
    """
    from agent_compiler.services.replay_service import ReplayService

    service = RunService(session)
    replay_service = ReplayService(session)

    # Verify run exists
    run_detail = await service.get_run_with_steps(run_id)
    if run_detail is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifacts = await replay_service.get_run_artifacts(run_id)

    return ArtifactsResponse(
        run_id=run_id,
        artifacts=artifacts,
    )


@router.get("/{run_id}/events")
async def get_run_events(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get fine-grained debug timeline events for a run.

    Returns one record per event emitted during execution:
    LLM_PROMPT, LLM_RESPONSE, TOOL_CALL, TOOL_RESULT,
    RETRIEVAL, ROUTER_DECISION, POLICY_BLOCK — ordered by seq.
    """
    service = RunService(session)
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return await service.get_run_events(run_id)


class DiffRequest(BaseModel):
    """Request body for run diff."""

    run_a: str = Field(description="ID of run A (baseline)")
    run_b: str = Field(description="ID of run B (comparison)")


@router.post("/diff")
async def diff_runs(
    diff_request: DiffRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Diff two runs and return per-step changes with summary stats.

    Aligns steps by node_id + step_order and computes structured diffs
    per field (output, duration, tokens, model).

    Summary stats include:
    - changed_nodes: nodes whose output changed
    - token_delta: total tokens B minus total tokens A
    - duration_delta_ms: total duration B minus total duration A
    - tool_failure_rate_a/b: fraction of Tool steps that failed
    """
    import json as _json

    run_a_id = diff_request.run_a
    run_b_id = diff_request.run_b

    service = RunService(session)
    run_a = await service.get_run_with_steps(run_a_id)
    run_b = await service.get_run_with_steps(run_b_id)

    if run_a is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_a_id}")
    if run_b is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_b_id}")

    steps_a: dict[str, Any] = {s["node_id"]: s for s in run_a.get("timeline", [])}
    steps_b: dict[str, Any] = {s["node_id"]: s for s in run_b.get("timeline", [])}
    all_nodes = sorted(set(list(steps_a.keys()) + list(steps_b.keys())))

    def _output_text(step: dict | None) -> str:
        if not step or not step.get("output"):
            return ""
        out = step["output"]
        if isinstance(out, dict) and "output" in out:
            return str(out["output"])
        return _json.dumps(out, indent=2) if isinstance(out, dict) else str(out)

    def _total_tokens(step: dict | None) -> int:
        if not step:
            return 0
        t = step.get("tokens") or {}
        return t.get("total") or 0

    def _duration(step: dict | None) -> float:
        if not step:
            return 0.0
        return step.get("duration_ms") or 0.0

    def _tool_failure_rate(steps: dict[str, Any]) -> float:
        tool_steps = [s for s in steps.values() if (s.get("node_type") or "").upper() == "TOOL"]
        if not tool_steps:
            return 0.0
        failed = sum(1 for s in tool_steps if s.get("status") == "failed")
        return failed / len(tool_steps)

    node_diffs = []
    total_tokens_a = total_tokens_b = 0
    total_dur_a = total_dur_b = 0.0

    for node_id in all_nodes:
        sa = steps_a.get(node_id)
        sb = steps_b.get(node_id)
        out_a = _output_text(sa)
        out_b = _output_text(sb)
        tok_a = _total_tokens(sa)
        tok_b = _total_tokens(sb)
        dur_a = _duration(sa)
        dur_b = _duration(sb)
        total_tokens_a += tok_a
        total_tokens_b += tok_b
        total_dur_a += dur_a
        total_dur_b += dur_b

        # Simple line-level diff for output
        lines_a = out_a.splitlines()
        lines_b = out_b.splitlines()
        removed = [l for l in lines_a if l not in lines_b]
        added = [l for l in lines_b if l not in lines_a]

        node_diffs.append({
            "node_id": node_id,
            "node_type": (sa or sb or {}).get("node_type", "unknown"),
            "status_a": sa["status"] if sa else "missing",
            "status_b": sb["status"] if sb else "missing",
            "output_changed": out_a != out_b,
            "output_diff": {"removed": removed[:20], "added": added[:20]},
            "tokens_a": tok_a,
            "tokens_b": tok_b,
            "token_delta": tok_b - tok_a,
            "duration_ms_a": dur_a,
            "duration_ms_b": dur_b,
            "duration_delta_ms": dur_b - dur_a,
            "model_a": sa.get("model_name") if sa else None,
            "model_b": sb.get("model_name") if sb else None,
        })

    changed = sum(1 for d in node_diffs if d["output_changed"])
    return {
        "run_a": {
            "id": run_a_id,
            "status": run_a["status"],
            "duration_ms": run_a.get("duration_ms"),
            "created_at": run_a.get("created_at"),
            "total_tokens": total_tokens_a,
        },
        "run_b": {
            "id": run_b_id,
            "status": run_b["status"],
            "duration_ms": run_b.get("duration_ms"),
            "created_at": run_b.get("created_at"),
            "total_tokens": total_tokens_b,
        },
        "summary": {
            "total_nodes": len(all_nodes),
            "changed_nodes": changed,
            "unchanged_nodes": len(all_nodes) - changed,
            "token_delta": total_tokens_b - total_tokens_a,
            "duration_delta_ms": total_dur_b - total_dur_a,
            "tool_failure_rate_a": _tool_failure_rate(steps_a),
            "tool_failure_rate_b": _tool_failure_rate(steps_b),
        },
        "node_diffs": node_diffs,
    }


@router.get("/{run_id}/compare/{other_run_id}")
async def compare_runs(
    run_id: str,
    other_run_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compare two runs side-by-side.

    Returns per-node diffs of outputs, duration, tokens, and model info.
    Useful for A/B testing prompt changes or model swaps.
    """
    import json

    service = RunService(session)

    run_a = await service.get_run_with_steps(run_id)
    run_b = await service.get_run_with_steps(other_run_id)

    if run_a is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    if run_b is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {other_run_id}")

    # Index steps by node_id for easy lookup
    steps_a = {s["node_id"]: s for s in run_a.get("timeline", [])}
    steps_b = {s["node_id"]: s for s in run_b.get("timeline", [])}

    all_nodes = sorted(set(list(steps_a.keys()) + list(steps_b.keys())))

    node_diffs = []
    for node_id in all_nodes:
        sa = steps_a.get(node_id)
        sb = steps_b.get(node_id)

        def _extract_output_text(step: dict | None) -> str:
            if not step or not step.get("output"):
                return ""
            out = step["output"]
            if isinstance(out, dict) and "output" in out:
                return str(out["output"])
            return json.dumps(out, indent=2) if isinstance(out, dict) else str(out)

        diff: dict[str, Any] = {
            "node_id": node_id,
            "node_type": (sa or sb or {}).get("node_type", "unknown"),
            "run_a": {
                "status": sa["status"] if sa else "missing",
                "duration_ms": sa.get("duration_ms") if sa else None,
                "output_preview": _extract_output_text(sa)[:500],
                "tokens": sa.get("tokens") if sa else None,
                "model_name": sa.get("model_name") if sa else None,
            },
            "run_b": {
                "status": sb["status"] if sb else "missing",
                "duration_ms": sb.get("duration_ms") if sb else None,
                "output_preview": _extract_output_text(sb)[:500],
                "tokens": sb.get("tokens") if sb else None,
                "model_name": sb.get("model_name") if sb else None,
            },
            "output_changed": _extract_output_text(sa) != _extract_output_text(sb),
        }
        node_diffs.append(diff)

    return {
        "run_a": {
            "id": run_id,
            "status": run_a["status"],
            "duration_ms": run_a.get("duration_ms"),
            "created_at": run_a.get("created_at"),
        },
        "run_b": {
            "id": other_run_id,
            "status": run_b["status"],
            "duration_ms": run_b.get("duration_ms"),
            "created_at": run_b.get("created_at"),
        },
        "node_diffs": node_diffs,
        "total_nodes": len(all_nodes),
        "changed_nodes": sum(1 for d in node_diffs if d["output_changed"]),
    }
