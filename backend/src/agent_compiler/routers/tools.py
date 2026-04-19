"""Tool Contracts API endpoints.

Provides:
  GET /tool-contracts            — list all registered tool contracts
  GET /tool-contracts/{name}     — get a single contract by tool name
  POST /tool-contracts/validate  — validate an IR payload's tool references
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent_compiler.tools.contracts import get_tool_contract_registry, ToolContract
from agent_compiler.observability.logging import get_logger

router = APIRouter(prefix="/tool-contracts", tags=["tool-contracts"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ToolContractSummary(BaseModel):
    """Lightweight summary used in list responses."""

    name: str
    version: str
    description: str
    contract_only: bool
    auth_type: str
    has_network_scope: bool
    has_data_scope: bool


class ToolContractDetail(BaseModel):
    """Full contract detail."""

    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    auth: dict[str, Any]
    network: dict[str, Any]
    data_access: dict[str, Any]
    policy: dict[str, Any]
    runtime: dict[str, Any]
    contract_only: bool


class ValidateToolRefsRequest(BaseModel):
    """Payload for the validate endpoint."""

    ir: dict[str, Any]
    allow_unknown: bool = True


class ValidateToolRefsResponse(BaseModel):
    """Result of tool reference validation."""

    valid: bool
    unknown_tools: list[str]
    warnings: list[str]
    tool_count: int
    tool_names: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_summary(c: ToolContract) -> ToolContractSummary:
    return ToolContractSummary(
        name=c.name,
        version=c.version,
        description=c.description,
        contract_only=c.contract_only,
        auth_type=c.auth.type if c.auth else "none",
        has_network_scope=bool(c.network and c.network.allowed_hosts),
        has_data_scope=bool(c.data_access and c.data_access.allowed_schemas),
    )


def _to_detail(c: ToolContract) -> ToolContractDetail:
    return ToolContractDetail(
        name=c.name,
        version=c.version,
        description=c.description,
        input_schema=c.input_schema,
        output_schema=c.output_schema,
        auth=c.auth.model_dump() if c.auth else {},
        network=c.network.model_dump() if c.network else {},
        data_access=c.data_access.model_dump() if c.data_access else {},
        policy=c.policy.model_dump() if c.policy else {},
        runtime=c.runtime.model_dump() if c.runtime else {},
        contract_only=c.contract_only,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ToolContractSummary])
async def list_tool_contracts() -> list[ToolContractSummary]:
    """List all registered tool contracts."""
    registry = get_tool_contract_registry()
    return [_to_summary(c) for c in registry.get_all()]


@router.get("/{tool_name}", response_model=ToolContractDetail)
async def get_tool_contract(tool_name: str) -> ToolContractDetail:
    """Get a single tool contract by name."""
    registry = get_tool_contract_registry()
    contract = registry.get(tool_name)
    if contract is None:
        raise HTTPException(
            status_code=404,
            detail=f"No contract registered for tool '{tool_name}'. "
            "MCP tools (mcp:*) are wildcards and have no individual contract.",
        )
    return _to_detail(contract)


@router.post("/validate", response_model=ValidateToolRefsResponse)
async def validate_tool_refs(request: ValidateToolRefsRequest) -> ValidateToolRefsResponse:
    """Validate tool references in an IR payload.

    Accepts a raw IR dict, parses it into FlowIRv2, and checks every TOOL
    node against the contract registry.

    Set ``allow_unknown=false`` to get a 422 when unknown tools are found.
    """
    from agent_compiler.models.ir_v2 import FlowIRv2
    from agent_compiler.ir.validate import (
        validate_tool_references,
        collect_tool_names,
        IRToolValidationError,
    )

    try:
        ir = FlowIRv2.model_validate(request.ir)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid IR payload: {exc}") from exc

    tool_names = list(collect_tool_names(ir).keys())

    try:
        warnings = validate_tool_references(ir, allow_unknown=request.allow_unknown)
        return ValidateToolRefsResponse(
            valid=True,
            unknown_tools=[],
            warnings=warnings,
            tool_count=len(tool_names),
            tool_names=tool_names,
        )
    except IRToolValidationError as exc:
        if not request.allow_unknown:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "IR references unknown tools",
                    "unknown_tools": exc.unknown_tools,
                },
            ) from exc
        return ValidateToolRefsResponse(
            valid=False,
            unknown_tools=exc.unknown_tools,
            warnings=[str(exc)],
            tool_count=len(tool_names),
            tool_names=tool_names,
        )
