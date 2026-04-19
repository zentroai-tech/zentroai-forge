"""Project Templates API endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.database import get_session
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.flow_service import FlowService
from agent_compiler.templates import (
    ProjectTemplateId,
    TargetEngine,
    TemplateFactory,
    get_template_registry,
)
from agent_compiler.templates.enums import get_template_version
from agent_compiler.templates.factory import TemplateValidationError

logger = get_logger(__name__)

router = APIRouter(prefix="/project-templates", tags=["templates"])


# =============================================================================
# Request/Response Models
# =============================================================================


class TemplateParamSchema(BaseModel):
    """Schema for a template parameter."""

    name: str
    type: str
    description: str
    default: Any
    required: bool
    options: list[str] | None = None


class TemplateTagSchema(BaseModel):
    """Schema for a template tag with label and color."""

    label: str
    color: str


class TemplateResponse(BaseModel):
    """Response model for a single template.

    Matches frontend TemplateDTO interface.
    """

    id: str
    name: str
    description: str
    tags: list[TemplateTagSchema]
    preview_type: str  # "blank", "rag", "simple_agent"
    default_engine: str
    supported_engines: list[str]
    # Optional fields for detailed views
    version: str | None = None
    params: list[TemplateParamSchema] | None = None


class CreateProjectRequest(BaseModel):
    """Request body for creating a project from template."""

    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    template_id: str = Field(
        default="blank",
        description="Template ID: 'blank', 'simple_agent', or 'rag_agent'",
    )
    engine: str = Field(
        default="langgraph",
        description="Target engine: 'langgraph' or 'llamaindex'",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional template-specific parameters",
    )

    @field_validator("template_id")
    @classmethod
    def validate_template_id(cls, v: str) -> str:
        """Validate template ID."""
        valid_ids = [t.value for t in ProjectTemplateId]
        if v not in valid_ids:
            raise ValueError(f"Invalid template_id. Must be one of: {valid_ids}")
        return v

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, v: str) -> str:
        """Validate engine."""
        valid_engines = [e.value for e in TargetEngine]
        if v not in valid_engines:
            raise ValueError(f"Invalid engine. Must be one of: {valid_engines}")
        return v


class CreateProjectResponse(BaseModel):
    """Response model for project creation.

    Matches frontend CreateProjectResponse interface.
    """

    id: str  # Frontend expects 'id' not 'project_id'
    name: str
    template_id: str
    engine: str
    created_at: str  # ISO timestamp


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[TemplateResponse])
async def list_templates() -> list[TemplateResponse]:
    """List all available project templates.

    Returns metadata for each template including:
    - ID, name, description
    - Tags with labels and colors for UI display
    - Preview type for diagram selection
    - Supported engines

    **Example Response:**
    ```json
    [
      {
        "id": "blank",
        "name": "Blank Project",
        "description": "Start with an empty canvas...",
        "tags": [{"label": "Minimal", "color": "#6b7280"}],
        "preview_type": "blank",
        "default_engine": "langgraph",
        "supported_engines": ["langgraph", "llamaindex"]
      },
      ...
    ]
    ```
    """
    registry = get_template_registry()
    templates = registry.get_all()

    return [
        TemplateResponse(
            id=t.id.value,
            name=t.name,
            description=t.description,
            tags=[
                TemplateTagSchema(label=tag.label, color=tag.color)
                for tag in t.tags
            ],
            preview_type=t.preview_type,
            supported_engines=[e.value for e in t.supported_engines],
            default_engine=t.default_engine.value,
            params=[
                TemplateParamSchema(
                    name=p.name,
                    type=p.type,
                    description=p.description,
                    default=p.default,
                    required=p.required,
                    options=p.options,
                )
                for p in t.params
            ],
        )
        for t in templates
    ]


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str) -> TemplateResponse:
    """Get details for a specific template.

    Args:
        template_id: Template identifier (blank, simple_agent, rag_agent)

    Returns:
        Template details including parameters and supported engines
    """
    # Validate template ID
    try:
        tid = ProjectTemplateId(template_id)
    except ValueError:
        valid_ids = [t.value for t in ProjectTemplateId]
        raise HTTPException(
            status_code=404,
            detail=f"Template not found: {template_id}. Valid IDs: {valid_ids}",
        )

    registry = get_template_registry()
    template = registry.get(tid)

    if template is None:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

    return TemplateResponse(
        id=template.id.value,
        name=template.name,
        description=template.description,
        tags=[
            TemplateTagSchema(label=tag.label, color=tag.color)
            for tag in template.tags
        ],
        preview_type=template.preview_type,
        supported_engines=[e.value for e in template.supported_engines],
        default_engine=template.default_engine.value,
        version=template.version,
        params=[
            TemplateParamSchema(
                name=p.name,
                type=p.type,
                description=p.description,
                default=p.default,
                required=p.required,
                options=p.options,
            )
            for p in template.params
        ],
    )


@router.post("/{template_id}/preview", response_model=dict[str, Any])
async def preview_template_ir(
    template_id: str,
    engine: str = "langgraph",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Preview the IR that would be generated for a template.

    Useful for UI previews without creating a project.

    Args:
        template_id: Template identifier
        engine: Target engine
        params: Optional template parameters

    Returns:
        Generated IR preview (not persisted)
    """
    # Validate template ID
    try:
        tid = ProjectTemplateId(template_id)
    except ValueError:
        valid_ids = [t.value for t in ProjectTemplateId]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template_id. Must be one of: {valid_ids}",
        )

    # Validate engine
    try:
        eng = TargetEngine(engine)
    except ValueError:
        valid_engines = [e.value for e in TargetEngine]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid engine. Must be one of: {valid_engines}",
        )

    # Validate params
    if params:
        errors = TemplateFactory.validate_params(tid, params)
        if errors:
            raise HTTPException(status_code=400, detail={"param_errors": errors})

    try:
        # Generate preview IR with placeholder IDs
        ir = TemplateFactory.create_ir(
            template_id=tid,
            engine=eng,
            project_id="preview",
            project_name="Preview Project",
            params=params or {},
        )

        return {
            "template_id": template_id,
            "engine": engine,
            "ir": ir.model_dump(),
        }

    except TemplateValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Projects Router Extension
# =============================================================================

projects_router = APIRouter(prefix="/projects", tags=["projects"])


@projects_router.post("", response_model=CreateProjectResponse, status_code=201)
async def create_project(
    request: CreateProjectRequest,
    session: AsyncSession = Depends(get_session),
) -> CreateProjectResponse:
    """Create a new project from a template.

    Generates initial IR based on the selected template and engine,
    persists the project, and returns the complete IR for the editor.

    **Request Body:**
    ```json
    {
      "name": "My RAG Bot",
      "template_id": "rag_agent",
      "engine": "llamaindex",
      "params": {
        "include_query_rewrite": true,
        "include_citations": true,
        "top_k": 5
      }
    }
    ```

    **Response:**
    ```json
    {
      "project_id": "my-rag-bot-abc123",
      "name": "My RAG Bot",
      "template_id": "rag_agent",
      "template_version": "1.0.0",
      "engine": "llamaindex",
      "created_from_template": true,
      "ir": { ... }
    }
    ```
    """
    # Parse enums
    template_id = ProjectTemplateId(request.template_id)
    engine = TargetEngine(request.engine)

    # Validate params
    if request.params:
        errors = TemplateFactory.validate_params(template_id, request.params)
        if errors:
            raise HTTPException(
                status_code=400,
                detail={"message": "Invalid parameters", "errors": errors},
            )

    # Generate project ID (slugified name + short UUID)
    slug = request.name.lower().replace(" ", "-")[:30]
    short_id = uuid.uuid4().hex[:8]
    project_id = f"{slug}-{short_id}"

    try:
        # Generate IR from template
        ir = TemplateFactory.create_ir(
            template_id=template_id,
            engine=engine,
            project_id=project_id,
            project_name=request.name,
            params=request.params,
        )

        # Log template creation
        logger.info(
            "Creating project from template",
            extra={
                "project_id": project_id,
                "template_id": template_id.value,
                "template_version": get_template_version(template_id),
                "engine": engine.value,
            },
        )

        # Persist via FlowService with template metadata
        flow_service = FlowService(session)
        flow = await flow_service.create_flow(
            ir_data=ir.model_dump(),
            template_id=template_id.value,
            template_version=get_template_version(template_id),
        )

        return CreateProjectResponse(
            id=flow.id,
            name=request.name,
            template_id=template_id.value,
            engine=engine.value,
            created_at=flow.created_at.isoformat() if flow.created_at else "",
        )

    except TemplateValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # Flow already exists or validation error
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Project creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create project")


@projects_router.post("/{project_id}/regenerate-from-template")
async def regenerate_from_template(
    project_id: str,
    engine: str | None = None,
    params: dict[str, Any] | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Regenerate a project's IR from its original template.

    **Admin/Dev only endpoint.**

    Useful for applying template updates or changing engine.
    Preserves the project ID and name.

    Args:
        project_id: Existing project ID
        engine: Optional new engine (keeps current if not specified)
        params: Optional new parameters (keeps current if not specified)

    Returns:
        Updated project with new IR
    """
    flow_service = FlowService(session)
    flow = await flow_service.get_flow(project_id)

    if flow is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    # For now, we don't store template_id in FlowRecord
    # This endpoint would need that metadata to work properly
    # Placeholder implementation:
    raise HTTPException(
        status_code=501,
        detail="Regeneration requires template metadata. Store template_id in FlowRecord.",
    )
