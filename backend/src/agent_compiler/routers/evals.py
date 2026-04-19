"""Eval suites API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.services.eval_service import EvalService

router = APIRouter(prefix="/evals", tags=["evals"])
_logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================


class SuiteCreate(BaseModel):
    """Request body for creating a suite."""

    name: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class SuiteResponse(BaseModel):
    """Response for suite operations."""

    id: str
    flow_id: str
    name: str
    description: str
    config: dict[str, Any]
    created_at: str
    updated_at: str


class CaseCreate(BaseModel):
    """Request body for creating a test case."""

    name: str
    description: str = ""
    input: dict[str, Any]
    expected: dict[str, Any] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CaseUpdate(BaseModel):
    """Request body for updating a test case."""

    name: str | None = None
    description: str | None = None
    input: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    assertions: list[dict[str, Any]] | None = None
    tags: list[str] | None = None


class CaseResponse(BaseModel):
    """Response for case operations."""

    id: str
    suite_id: str
    name: str
    description: str
    input: dict[str, Any]
    expected: dict[str, Any]
    assertions: list[dict[str, Any]]
    tags: list[str]
    created_at: str


class EvalRunResponse(BaseModel):
    """Response for eval run operations."""

    id: str
    suite_id: str
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    gate_passed: bool | None
    started_at: str | None
    finished_at: str | None
    created_at: str


class CaseResultResponse(BaseModel):
    """Response for case result."""

    id: str
    case_id: str
    run_id: str | None
    status: str
    assertions: list[dict[str, Any]]
    error_message: str | None
    duration_ms: float | None


class RunSuiteRequest(BaseModel):
    """Request body for running a suite."""

    tags: list[str] | None = Field(
        default=None,
        description="Optional filter to run only cases with specific tags",
    )


# =============================================================================
# Suite Endpoints
# =============================================================================


@router.post("/flows/{flow_id}/suites", response_model=SuiteResponse, status_code=201)
async def create_suite(
    flow_id: str,
    suite_data: SuiteCreate,
    session: AsyncSession = Depends(get_session),
) -> SuiteResponse:
    """Create a new eval suite for a flow."""
    service = EvalService(session)

    suite = await service.create_suite(
        flow_id=flow_id,
        name=suite_data.name,
        description=suite_data.description,
        config=suite_data.config,
    )

    return SuiteResponse(
        id=suite.id,
        flow_id=suite.flow_id,
        name=suite.name,
        description=suite.description,
        config=suite.config,
        created_at=suite.created_at.isoformat(),
        updated_at=suite.updated_at.isoformat(),
    )


@router.get("/flows/{flow_id}/suites", response_model=list[SuiteResponse])
async def list_suites(
    flow_id: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[SuiteResponse]:
    """List eval suites for a flow."""
    service = EvalService(session)
    suites = await service.list_suites(flow_id=flow_id, limit=limit, offset=offset)

    return [
        SuiteResponse(
            id=s.id,
            flow_id=s.flow_id,
            name=s.name,
            description=s.description,
            config=s.config,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in suites
    ]


@router.get("/suites/{suite_id}", response_model=SuiteResponse)
async def get_suite(
    suite_id: str,
    session: AsyncSession = Depends(get_session),
) -> SuiteResponse:
    """Get a suite by ID."""
    service = EvalService(session)
    suite = await service.get_suite(suite_id)

    if not suite:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_id}")

    return SuiteResponse(
        id=suite.id,
        flow_id=suite.flow_id,
        name=suite.name,
        description=suite.description,
        config=suite.config,
        created_at=suite.created_at.isoformat(),
        updated_at=suite.updated_at.isoformat(),
    )


@router.patch("/suites/{suite_id}/config", response_model=SuiteResponse)
async def update_suite_config(
    suite_id: str,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> SuiteResponse:
    """Update a suite's config (e.g. thresholds)."""
    import json as _json
    service = EvalService(session)
    suite = await service.get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_id}")

    new_config = body.get("config", {})
    suite.config_json = _json.dumps(new_config)
    from datetime import datetime, timezone
    suite.updated_at = datetime.now(timezone.utc)
    session.add(suite)
    await session.commit()
    await session.refresh(suite)

    return SuiteResponse(
        id=suite.id,
        flow_id=suite.flow_id,
        name=suite.name,
        description=suite.description,
        config=suite.config,
        created_at=suite.created_at.isoformat(),
        updated_at=suite.updated_at.isoformat(),
    )


@router.delete("/suites/{suite_id}", status_code=204)
async def delete_suite(
    suite_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a suite."""
    service = EvalService(session)
    deleted = await service.delete_suite(suite_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_id}")


# =============================================================================
# Case Endpoints
# =============================================================================


@router.post("/suites/{suite_id}/cases", response_model=CaseResponse, status_code=201)
async def create_case(
    suite_id: str,
    case_data: CaseCreate,
    session: AsyncSession = Depends(get_session),
) -> CaseResponse:
    """Create a new test case in a suite."""
    import json

    service = EvalService(session)

    # Verify suite exists
    suite = await service.get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_id}")

    case = await service.create_case(
        suite_id=suite_id,
        name=case_data.name,
        description=case_data.description,
        input_data=case_data.input,
        expected_data=case_data.expected,
        assertions=case_data.assertions,
        tags=case_data.tags,
    )

    return CaseResponse(
        id=case.id,
        suite_id=case.suite_id,
        name=case.name,
        description=case.description,
        input=case.input_data,
        expected=case.expected_data,
        assertions=case.assertions,
        tags=json.loads(case.tags) if case.tags else [],
        created_at=case.created_at.isoformat(),
    )


@router.get("/suites/{suite_id}/cases", response_model=list[CaseResponse])
async def list_cases(
    suite_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[CaseResponse]:
    """List cases in a suite."""
    import json

    service = EvalService(session)

    # Verify suite exists
    suite = await service.get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_id}")

    cases = await service.list_cases(suite_id)

    return [
        CaseResponse(
            id=c.id,
            suite_id=c.suite_id,
            name=c.name,
            description=c.description,
            input=c.input_data,
            expected=c.expected_data,
            assertions=c.assertions,
            tags=json.loads(c.tags) if c.tags else [],
            created_at=c.created_at.isoformat(),
        )
        for c in cases
    ]


@router.put("/cases/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    case_data: CaseUpdate,
    session: AsyncSession = Depends(get_session),
) -> CaseResponse:
    """Update an existing test case."""
    import json

    service = EvalService(session)
    case = await service.update_case(
        case_id,
        name=case_data.name,
        description=case_data.description,
        input_data=case_data.input,
        expected_data=case_data.expected,
        assertions=case_data.assertions,
        tags=case_data.tags,
    )
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    return CaseResponse(
        id=case.id,
        suite_id=case.suite_id,
        name=case.name,
        description=case.description,
        input=case.input_data,
        expected=case.expected_data,
        assertions=case.assertions,
        tags=json.loads(case.tags) if case.tags else [],
        created_at=case.created_at.isoformat(),
    )


@router.delete("/cases/{case_id}", status_code=204)
async def delete_case(
    case_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a test case."""
    service = EvalService(session)
    deleted = await service.delete_case(case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")


# =============================================================================
# Run Endpoints
# =============================================================================


@router.post("/suites/{suite_id}/run", response_model=EvalRunResponse, status_code=201)
async def run_suite(
    suite_id: str,
    request: RunSuiteRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> EvalRunResponse:
    """Run all cases in a suite."""
    service = EvalService(session)

    try:
        tags = request.tags if request else None
        eval_run = await service.run_suite(suite_id, tags=tags)

        return EvalRunResponse(
            id=eval_run.id,
            suite_id=eval_run.suite_id,
            status=eval_run.status.value,
            total_cases=eval_run.total_cases,
            passed_cases=eval_run.passed_cases,
            failed_cases=eval_run.failed_cases,
            gate_passed=eval_run.gate_passed,
            started_at=eval_run.started_at.isoformat() if eval_run.started_at else None,
            finished_at=eval_run.finished_at.isoformat() if eval_run.finished_at else None,
            created_at=eval_run.created_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        _logger.error("Eval run execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error. Check server logs.")


@router.get("/suites/{suite_id}/runs", response_model=list[EvalRunResponse])
async def list_eval_runs(
    suite_id: str,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[EvalRunResponse]:
    """List eval runs for a suite."""
    service = EvalService(session)

    runs = await service.list_eval_runs(suite_id, limit=limit)

    return [
        EvalRunResponse(
            id=r.id,
            suite_id=r.suite_id,
            status=r.status.value,
            total_cases=r.total_cases,
            passed_cases=r.passed_cases,
            failed_cases=r.failed_cases,
            gate_passed=r.gate_passed,
            started_at=r.started_at.isoformat() if r.started_at else None,
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@router.get("/runs/{eval_run_id}", response_model=EvalRunResponse)
async def get_eval_run(
    eval_run_id: str,
    session: AsyncSession = Depends(get_session),
) -> EvalRunResponse:
    """Get an eval run by ID."""
    service = EvalService(session)
    eval_run = await service.get_eval_run(eval_run_id)

    if not eval_run:
        raise HTTPException(status_code=404, detail=f"Eval run not found: {eval_run_id}")

    return EvalRunResponse(
        id=eval_run.id,
        suite_id=eval_run.suite_id,
        status=eval_run.status.value,
        total_cases=eval_run.total_cases,
        passed_cases=eval_run.passed_cases,
        failed_cases=eval_run.failed_cases,
        gate_passed=eval_run.gate_passed,
        started_at=eval_run.started_at.isoformat() if eval_run.started_at else None,
        finished_at=eval_run.finished_at.isoformat() if eval_run.finished_at else None,
        created_at=eval_run.created_at.isoformat(),
    )


@router.get("/runs/{eval_run_id}/results", response_model=list[CaseResultResponse])
async def get_case_results(
    eval_run_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[CaseResultResponse]:
    """Get all case results for an eval run."""
    service = EvalService(session)

    results = await service.get_case_results(eval_run_id)

    return [
        CaseResultResponse(
            id=r.id,
            case_id=r.case_id,
            run_id=r.run_id,
            status=r.status.value,
            assertions=r.assertion_results,
            error_message=r.error_message,
            duration_ms=r.duration_ms,
        )
        for r in results
    ]


@router.get("/runs/{eval_run_id}/report")
async def get_eval_report(
    eval_run_id: str,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Download the JSON report for an eval run."""
    service = EvalService(session)
    report = await service.get_report(eval_run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report not found for run: {eval_run_id}")
    return JSONResponse(
        content=report,
        headers={"Content-Disposition": f"attachment; filename=eval_report_{eval_run_id}.json"},
    )


# =============================================================================
# Dataset Upload Endpoints
# =============================================================================


class DatasetImportResponse(BaseModel):
    """Response after importing a JSONL dataset."""

    suite_id: str
    imported_cases: int
    case_ids: list[str]


@router.post("/suites/{suite_id}/dataset", response_model=DatasetImportResponse, status_code=201)
async def upload_dataset(
    suite_id: str,
    file: UploadFile = File(..., description="JSONL file — one JSON object per line"),
    session: AsyncSession = Depends(get_session),
) -> DatasetImportResponse:
    """Upload a JSONL dataset file and create eval cases from it.

    Each line in the file must be a JSON object with at least an "input" field.
    Optional fields: id, expected, assertions, tags.

    Example line:
        {"id": "case-001", "input": "What is 2+2?", "expected": {"answer": "4"}}
    """
    service = EvalService(session)

    # Verify suite exists
    suite = await service.get_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_id}")

    # Read file content
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    # Import JSONL
    try:
        cases = await service.import_dataset_jsonl(suite_id, content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return DatasetImportResponse(
        suite_id=suite_id,
        imported_cases=len(cases),
        case_ids=[c.id for c in cases],
    )
