"""Export and code preview API endpoints."""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.models.db import ExportStatus
from agent_compiler.services.preview_service import PreviewService

router = APIRouter(prefix="/exports", tags=["exports"])
_logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================

class FileEntry(BaseModel):
    """A file entry in the manifest."""

    path: str
    size: int
    language: str
    sha256: str


class ManifestLimits(BaseModel):
    """Limits applied to manifest generation."""

    max_file_bytes: int
    max_total_files: int


class ManifestResponse(BaseModel):
    """Response for manifest endpoint."""

    export_id: str
    flow_id: str | None = None
    flow_name: str | None = None
    target: str = "langgraph"
    root: str
    ir_version: str
    created_at: str
    total_files: int
    files: list[FileEntry]
    entrypoints: list[str]
    truncated: bool
    limits: ManifestLimits


class FileContentResponse(BaseModel):
    """Response for file content endpoint."""

    path: str
    content: str
    encoding: str = "utf-8"
    truncated: bool
    size: int
    sha256: str
    language: str


class ExportInfoResponse(BaseModel):
    """Basic export info response."""

    export_id: str
    flow_id: str
    status: str
    target: str = "langgraph"
    created_at: str
    download_url: str
    manifest_url: str


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{export_id}/manifest", response_model=ManifestResponse)
async def get_manifest(
    export_id: str,
    session: AsyncSession = Depends(get_session),
) -> ManifestResponse:
    """Get the manifest for an export.

    Returns a JSON manifest listing all previewable files with metadata.
    Files are filtered to exclude binaries and sensitive files.

    Args:
        export_id: The export ID

    Returns:
        ManifestResponse with file listing

    Raises:
        404: Export not found
        500: Export directory missing
    """
    from agent_compiler.services.flow_service import FlowService

    service = PreviewService(session)
    export = await service.get_export(export_id)

    if export is None:
        raise HTTPException(status_code=404, detail=f"Export not found: {export_id}")

    if export.status != ExportStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Export not ready. Status: {export.status.value}",
        )

    # Get flow name for manifest
    flow_name = None
    try:
        flow_service = FlowService(session)
        flow = await flow_service.get_flow(export.flow_id)
        if flow:
            flow_name = flow.name
    except Exception:
        pass  # Flow might have been deleted

    try:
        manifest = await service.get_or_generate_manifest(export, flow_name=flow_name)
        return ManifestResponse(**manifest)
    except FileNotFoundError:
        _logger.error("Export manifest generation failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error. Check server logs.")


@router.get("/{export_id}/file", response_model=FileContentResponse)
async def get_file(
    export_id: str,
    path: str = Query(..., description="Relative path to the file within the export"),
    session: AsyncSession = Depends(get_session),
) -> FileContentResponse:
    """Get the content of a single file from an export.

    Returns UTF-8 text content. Binary files are rejected.
    Large files are truncated to max_file_bytes.
    Sensitive content (API keys, passwords) is redacted.

    Args:
        export_id: The export ID
        path: Relative file path (e.g., "src/agent_app/main.py")

    Returns:
        FileContentResponse with file content

    Raises:
        404: Export or file not found
        403: File access forbidden (sensitive file)
        415: File is binary/non-text
    """
    service = PreviewService(session)
    export = await service.get_export(export_id)

    if export is None:
        raise HTTPException(status_code=404, detail=f"Export not found: {export_id}")

    if export.status != ExportStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Export not ready. Status: {export.status.value}",
        )

    try:
        # Get manifest for validation
        manifest = await service.get_or_generate_manifest(export)
        file_data = await service.get_file_content(export, path, manifest)
        return FileContentResponse(**file_data)

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        # Binary or non-UTF-8 file
        raise HTTPException(status_code=415, detail=str(e))


@router.get("/{export_id}/download")
async def download_export(
    export_id: str,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Download the export as a ZIP file.

    Args:
        export_id: The export ID

    Returns:
        ZIP file download

    Raises:
        404: Export not found or ZIP file missing
    """
    service = PreviewService(session)
    export = await service.get_export(export_id)

    if export is None:
        raise HTTPException(status_code=404, detail=f"Export not found: {export_id}")

    if export.status != ExportStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Export not ready. Status: {export.status.value}",
        )

    if not export.zip_path:
        raise HTTPException(status_code=404, detail="ZIP file path not set")

    zip_path = Path(export.zip_path)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="ZIP file not found on server")

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


@router.get("/{export_id}", response_model=ExportInfoResponse)
async def get_export_info(
    export_id: str,
    session: AsyncSession = Depends(get_session),
) -> ExportInfoResponse:
    """Get information about an export.

    Args:
        export_id: The export ID

    Returns:
        Export information including URLs

    Raises:
        404: Export not found
    """
    service = PreviewService(session)
    export = await service.get_export(export_id)

    if export is None:
        raise HTTPException(status_code=404, detail=f"Export not found: {export_id}")

    return ExportInfoResponse(
        export_id=export.id,
        flow_id=export.flow_id,
        status=export.status.value,
        target=export.target or "langgraph",
        created_at=export.created_at.isoformat(),
        download_url=f"/exports/{export.id}/download",
        manifest_url=f"/exports/{export.id}/manifest",
    )
