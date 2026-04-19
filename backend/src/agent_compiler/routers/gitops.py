"""GitOps API endpoints for GitHub integration and PR creation.

Endpoints:
- GET  /gitops/status              → GitHub connection status
- POST /gitops/connect             → Save GitHub PAT
- DELETE /gitops/disconnect        → Remove GitHub credential
- GET  /gitops/repos               → List user repos
- GET  /gitops/repos/{owner}/{repo}/branches → List branches
- GET  /gitops/jobs/{job_id}       → Poll job status
- POST /exports/{export_id}/gitops → Start PR creation job (separate router)
"""

import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_engine, get_session
from agent_compiler.models.credentials import (
    CredentialCreate,
    CredentialProvider,
    CredentialScopeType,
)
from agent_compiler.models.db import ExportStatus
from agent_compiler.services.credential_service import CredentialService
from agent_compiler.services.github_client import GitHubApiError, GitHubClient
from agent_compiler.services.gitops_service import GitOpsService
from agent_compiler.services.preview_service import PreviewService

# Main gitops router
router = APIRouter(prefix="/gitops", tags=["gitops"])

# Separate router for the /exports/{id}/gitops endpoint (no prefix)
exports_gitops_router = APIRouter(tags=["gitops"])

# Default scope for GitHub credential
GITHUB_SCOPE_TYPE = CredentialScopeType.WORKSPACE
GITHUB_SCOPE_ID = "default"


# =============================================================================
# Request/Response Models
# =============================================================================


class GitOpsConnectRequest(BaseModel):
    token: str = Field(..., description="GitHub Personal Access Token")


class GitOpsStatusResponse(BaseModel):
    configured: bool
    username: str | None = None
    default_repo: str | None = None
    permissions: list[str] | None = None


class GitOpsExportRequest(BaseModel):
    repo: str = Field(..., description="Repository in owner/name format")
    base_branch: str = Field(default="main")
    branch_name: str = Field(..., description="New branch name")
    target_path: str | None = None
    pr_title: str = Field(default="Agent export")
    pr_body: str = Field(default="")
    dry_run: bool = False

    @field_validator("branch_name")
    @classmethod
    def validate_branch_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9._/-]{1,100}$", v):
            raise ValueError(
                "Invalid branch name: only alphanumeric, '.', '_', '/', '-' allowed (max 100 chars)"
            )
        return v


class GitOpsExportResponse(BaseModel):
    job_id: str
    status: str
    message: str


# =============================================================================
# Helper to resolve GitHub token
# =============================================================================


async def _resolve_github_token(session: AsyncSession) -> str | None:
    """Try to resolve GitHub token, return None if not found."""
    svc = CredentialService(session)
    try:
        return await svc.resolve_credential(
            provider=CredentialProvider.GITHUB,
            workspace_id=GITHUB_SCOPE_ID,
        )
    except Exception:
        return None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/status", response_model=GitOpsStatusResponse)
async def get_gitops_status(
    session: AsyncSession = Depends(get_session),
) -> GitOpsStatusResponse:
    """Check GitHub connection status."""
    token = await _resolve_github_token(session)
    if not token:
        return GitOpsStatusResponse(configured=False)

    try:
        client = GitHubClient(token)
        user = await client.get_user()
        await client.close()
        return GitOpsStatusResponse(
            configured=True,
            username=user.get("login"),
        )
    except Exception:
        return GitOpsStatusResponse(configured=False)


@router.post("/connect")
async def connect_github(
    request: GitOpsConnectRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Save a GitHub PAT after validating it."""
    # Validate token
    client = GitHubClient(request.token)
    try:
        user = await client.get_user()
    except GitHubApiError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid GitHub token: {e}"
        )
    finally:
        await client.close()

    username = user.get("login", "unknown")

    # Delete any existing GitHub credential for this scope
    svc = CredentialService(session)
    existing = await svc.list_credentials(
        provider=CredentialProvider.GITHUB,
        scope_type=GITHUB_SCOPE_TYPE,
        scope_id=GITHUB_SCOPE_ID,
    )
    for cred in existing:
        await svc.delete_credential(cred.id)

    # Create new credential
    await svc.create_credential(
        CredentialCreate(
            provider=CredentialProvider.GITHUB,
            scope_type=GITHUB_SCOPE_TYPE,
            scope_id=GITHUB_SCOPE_ID,
            name=f"GitHub ({username})",
            secret=request.token,
        )
    )

    return {"status": "connected", "username": username}


@router.delete("/disconnect")
async def disconnect_github(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Remove GitHub credential."""
    svc = CredentialService(session)
    existing = await svc.list_credentials(
        provider=CredentialProvider.GITHUB,
        scope_type=GITHUB_SCOPE_TYPE,
        scope_id=GITHUB_SCOPE_ID,
    )
    for cred in existing:
        await svc.delete_credential(cred.id)
    return {"status": "disconnected"}


@router.get("/repos")
async def list_repos(
    query: str = "",
    page: int = 1,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List GitHub repositories for the authenticated user."""
    token = await _resolve_github_token(session)
    if not token:
        raise HTTPException(status_code=400, detail="GitHub not configured")

    client = GitHubClient(token)
    try:
        repos = await client.list_repos(query=query or None, page=page)
        return [
            {
                "full_name": r.get("full_name"),
                "private": r.get("private", False),
                "default_branch": r.get("default_branch", "main"),
                "description": r.get("description"),
            }
            for r in repos
        ]
    except GitHubApiError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    finally:
        await client.close()


@router.get("/repos/{owner}/{repo}/branches")
async def list_branches(
    owner: str,
    repo: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, str]]:
    """List branches for a repository."""
    token = await _resolve_github_token(session)
    if not token:
        raise HTTPException(status_code=400, detail="GitHub not configured")

    client = GitHubClient(token)
    try:
        branches = await client.list_branches(owner, repo)
        return [{"name": b.get("name")} for b in branches]
    except GitHubApiError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    finally:
        await client.close()


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Poll a GitOps job status."""
    engine = get_engine()
    svc = GitOpsService(engine)
    job = await svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


# =============================================================================
# Export GitOps endpoint (mounted at /exports/{export_id}/gitops)
# =============================================================================


@exports_gitops_router.post(
    "/exports/{export_id}/gitops", response_model=GitOpsExportResponse
)
async def create_gitops_export(
    export_id: str,
    request: GitOpsExportRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> GitOpsExportResponse:
    """Start a PR creation job for an export."""
    # Validate export exists and is ready
    preview_service = PreviewService(session)
    export = await preview_service.get_export(export_id)
    if not export:
        raise HTTPException(status_code=404, detail=f"Export not found: {export_id}")
    if export.status != ExportStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Export not ready. Status: {export.status.value}",
        )
    if not export.export_dir_path:
        raise HTTPException(status_code=400, detail="Export directory not set")

    # Validate repo format
    if "/" not in request.repo:
        raise HTTPException(
            status_code=400, detail="Repository must be in owner/name format"
        )

    # Resolve GitHub token
    token = await _resolve_github_token(session)
    if not token:
        raise HTTPException(status_code=400, detail="GitHub not configured")

    # Create job
    engine = get_engine()
    svc = GitOpsService(engine)
    job_id = await svc.create_job(
        export_id=export_id,
        repo=request.repo,
        base_branch=request.base_branch,
        branch_name=request.branch_name,
        pr_title=request.pr_title,
        pr_body=request.pr_body,
    )

    # Launch background task
    background_tasks.add_task(
        svc.execute_job,
        job_id=job_id,
        export_dir=export.export_dir_path,
        token=token,
        dry_run=request.dry_run,
    )

    return GitOpsExportResponse(
        job_id=job_id,
        status="pending",
        message="Job created, PR creation started in background",
    )
