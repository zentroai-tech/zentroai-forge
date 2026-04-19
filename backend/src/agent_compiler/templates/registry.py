"""Template Registry for managing template definitions.

Provides metadata and configuration for each template type.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from agent_compiler.templates.enums import (
    ProjectTemplateId,
    TargetEngine,
    get_template_version,
)


@dataclass(frozen=True)
class TemplateTag:
    """A tag with label and color for UI display."""

    label: str
    color: str  # Hex color code


@dataclass(frozen=True)
class TemplateParam:
    """Definition of a template parameter."""

    name: str
    type: str  # "boolean", "string", "integer", "select"
    description: str
    default: Any
    required: bool = False
    options: list[str] | None = None  # For select type


# Preview type for the frontend to select the right preview diagram
PreviewType = Literal["blank", "rag", "simple_agent", "supervisor_workers"]

# Curated LLM model list shown in the "model" selector across all templates.
# Ordered by provider then capability tier: flagship → balanced → fast.
_CURATED_MODELS: list[str] = [
    # OpenAI
    "gpt-4o",
    "gpt-4o-mini",
    "o3-mini",
    # Anthropic
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    # Google
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


@dataclass(frozen=True)
class TemplateDefinition:
    """Definition of a project template with metadata."""

    id: ProjectTemplateId
    name: str
    description: str
    supported_engines: tuple[TargetEngine, ...]
    default_engine: TargetEngine
    preview_type: PreviewType
    params: tuple[TemplateParam, ...] = field(default_factory=tuple)
    tags: tuple[TemplateTag, ...] = field(default_factory=tuple)

    @property
    def version(self) -> str:
        """Get the template version."""
        return get_template_version(self.id)

    def supports_engine(self, engine: TargetEngine) -> bool:
        """Check if this template supports the given engine."""
        return engine in self.supported_engines

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id.value,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "supported_engines": [e.value for e in self.supported_engines],
            "default_engine": self.default_engine.value,
            "preview_type": self.preview_type,
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "default": p.default,
                    "required": p.required,
                    "options": p.options,
                }
                for p in self.params
            ],
            "tags": [{"label": t.label, "color": t.color} for t in self.tags],
        }


# =============================================================================
# Template Definitions
# =============================================================================

BLANK_TEMPLATE = TemplateDefinition(
    id=ProjectTemplateId.BLANK,
    name="Blank Project",
    description="Start with an empty canvas and build your agent from scratch.",
    supported_engines=(TargetEngine.LANGGRAPH, TargetEngine.LLAMAINDEX),
    default_engine=TargetEngine.LANGGRAPH,
    preview_type="blank",
    params=(),
    tags=(TemplateTag(label="Minimal", color="#6b7280"),),
)

SIMPLE_AGENT_TEMPLATE = TemplateDefinition(
    id=ProjectTemplateId.SIMPLE_AGENT,
    name="Simple Agent Project",
    description=(
        "Basic agent with LLM and tool calling capabilities. Perfect for getting started."
    ),
    supported_engines=(TargetEngine.LANGGRAPH, TargetEngine.LLAMAINDEX),
    default_engine=TargetEngine.LANGGRAPH,
    preview_type="simple_agent",
    params=(
        TemplateParam(
            name="include_memory",
            type="boolean",
            description="Include a memory node for conversation history",
            default=True,
            required=False,
        ),
        TemplateParam(
            name="model",
            type="select",
            description="Default LLM model to use",
            default="gpt-4o-mini",
            required=False,
            options=_CURATED_MODELS,
        ),
        TemplateParam(
            name="tools",
            type="select",
            description="Pre-configured tool set",
            default="basic",
            required=False,
            options=["none", "basic", "web_search", "code_interpreter"],
        ),
    ),
    tags=(
        TemplateTag(label="Tools", color="#f59e0b"),
        TemplateTag(label="Agent", color="#ec4899"),
    ),
)

RAG_AGENT_TEMPLATE = TemplateDefinition(
    id=ProjectTemplateId.RAG_AGENT,
    name="RAG Agent Project",
    description=(
        "Pre-configured retrieval-augmented generation pipeline with grounding and citations."
    ),
    supported_engines=(TargetEngine.LANGGRAPH, TargetEngine.LLAMAINDEX),
    default_engine=TargetEngine.LANGGRAPH,
    preview_type="rag",
    params=(
        TemplateParam(
            name="include_query_rewrite",
            type="boolean",
            description="Include query rewriting for better retrieval",
            default=True,
            required=False,
        ),
        TemplateParam(
            name="include_reranker",
            type="boolean",
            description="Include a reranker for improved relevance",
            default=False,
            required=False,
        ),
        TemplateParam(
            name="include_citations",
            type="boolean",
            description="Include citation tracking and abstain guard",
            default=True,
            required=False,
        ),
        TemplateParam(
            name="top_k",
            type="integer",
            description="Number of documents to retrieve",
            default=5,
            required=False,
        ),
        TemplateParam(
            name="model",
            type="select",
            description="Default LLM model to use",
            default="gpt-4o-mini",
            required=False,
            options=_CURATED_MODELS,
        ),
    ),
    tags=(
        TemplateTag(label="RAG", color="#3b82f6"),
        TemplateTag(label="Citations", color="#10b981"),
        TemplateTag(label="Grounding", color="#8b5cf6"),
    ),
)


SUPERVISOR_WORKERS_TEMPLATE = TemplateDefinition(
    id=ProjectTemplateId.SUPERVISOR_WORKERS,
    name="Supervisor + Workers",
    description=(
        "Multi-agent architecture with a supervisor routing tasks to specialized "
        "worker agents (researcher + writer). Demonstrates handoffs and tool isolation."
    ),
    supported_engines=(TargetEngine.LANGGRAPH,),
    default_engine=TargetEngine.LANGGRAPH,
    preview_type="supervisor_workers",
    params=(
        TemplateParam(
            name="model",
            type="select",
            description="Default LLM model for all agents",
            default="gpt-4o-mini",
            required=False,
            options=_CURATED_MODELS,
        ),
        TemplateParam(
            name="num_workers",
            type="integer",
            description="Number of worker agents (2-4)",
            default=2,
            required=False,
        ),
    ),
    tags=(
        TemplateTag(label="Multi-Agent", color="#7c3aed"),
        TemplateTag(label="Supervisor", color="#f59e0b"),
        TemplateTag(label="Handoffs", color="#10b981"),
    ),
)

ONCOLOGY_RESEARCH_TEAM_TEMPLATE = TemplateDefinition(
    id=ProjectTemplateId.ONCOLOGY_RESEARCH_TEAM,
    name="Oncology Research Team",
    description=(
        "Multi-agent team for cancer research workflows. A supervisor routes requests to "
        "specialists in genomics, computational pathology, and clinical trials."
    ),
    supported_engines=(TargetEngine.LANGGRAPH,),
    default_engine=TargetEngine.LANGGRAPH,
    preview_type="supervisor_workers",
    params=(
        TemplateParam(
            name="model",
            type="select",
            description="Default LLM model for all specialist agents",
            default="gpt-4o-mini",
            required=False,
            options=_CURATED_MODELS,
        ),
        TemplateParam(
            name="include_pathology",
            type="boolean",
            description="Include a computational pathology specialist",
            default=True,
            required=False,
        ),
        TemplateParam(
            name="include_clinical_trials",
            type="boolean",
            description="Include a clinical trials specialist",
            default=True,
            required=False,
        ),
    ),
    tags=(
        TemplateTag(label="Multi-Agent", color="#7c3aed"),
        TemplateTag(label="Oncology", color="#dc2626"),
        TemplateTag(label="Research", color="#0ea5e9"),
    ),
)

FULLSTACK_MULTIAGENT_TEMPLATE = TemplateDefinition(
    id=ProjectTemplateId.FULLSTACK_MULTIAGENT,
    name="Forge Full-Stack Multi-Agent",
    description=(
        "Comprehensive multi-agent topology that exercises almost all Forge node types: "
        "LLM, Router, Retriever, Memory, Tool, Output, Parallel, Join, and Error; "
        "including v2.1 policies, retry/fallback, and schema-aware handoffs."
    ),
    supported_engines=(TargetEngine.LANGGRAPH,),
    default_engine=TargetEngine.LANGGRAPH,
    preview_type="supervisor_workers",
    params=(
        TemplateParam(
            name="model",
            type="select",
            description="Default LLM model for all agents",
            default="gpt-4o-mini",
            required=False,
            options=_CURATED_MODELS,
        ),
        TemplateParam(
            name="strict_schema",
            type="boolean",
            description="If true, schema validation errors fail execution",
            default=False,
            required=False,
        ),
        TemplateParam(
            name="include_mcp_tool",
            type="boolean",
            description="If true, Tool agent defaults to an MCP tool name",
            default=True,
            required=False,
        ),
    ),
    tags=(
        TemplateTag(label="Multi-Agent", color="#7c3aed"),
        TemplateTag(label="All Nodes", color="#0ea5e9"),
        TemplateTag(label="Policy/Retry", color="#f59e0b"),
    ),
)

PHARMA_RESEARCH_COPILOT_TEMPLATE = TemplateDefinition(
    id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
    name="Pharma Research Copilot (RAG + Tools + QA)",
    description=(
        "RAG with citations + tool execution (PubMed/SQL/API/Python/S3) + strict validation "
        "+ synthesis + recovery. NOTE: sql_query, http_request, python_sandbox, s3_get_object "
        "are contract tool names that require external implementation/config."
    ),
    supported_engines=(TargetEngine.LANGGRAPH,),
    default_engine=TargetEngine.LANGGRAPH,
    preview_type="supervisor_workers",
    params=(
        TemplateParam(
            name="model",
            type="select",
            description="Default LLM model for all agents",
            default="gpt-4o-mini",
            required=False,
            options=_CURATED_MODELS,
        ),
        TemplateParam(
            name="strict_schema",
            type="boolean",
            description="If true, schema validation errors fail execution",
            default=False,
            required=False,
        ),
        TemplateParam(
            name="vector_db_provider",
            type="select",
            description="Vector database provider for semantic indexing/search (adds vector_indexer agent)",
            default="none",
            required=False,
            options=["none", "qdrant", "pinecone"],
        ),
    ),
    tags=(
        TemplateTag(label="Multi-Agent", color="#7c3aed"),
        TemplateTag(label="Pharma/RAG", color="#0ea5e9"),
        TemplateTag(label="QA", color="#10b981"),
        TemplateTag(label="Policy/Retry", color="#f59e0b"),
        TemplateTag(label="Vector DB", color="#6366f1"),
    ),
)


# =============================================================================
# Template Registry
# =============================================================================


class TemplateRegistry:
    """Registry of available project templates."""

    def __init__(self) -> None:
        self._templates: dict[ProjectTemplateId, TemplateDefinition] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default templates."""
        self.register(BLANK_TEMPLATE)
        self.register(SIMPLE_AGENT_TEMPLATE)
        self.register(RAG_AGENT_TEMPLATE)
        self.register(SUPERVISOR_WORKERS_TEMPLATE)
        self.register(ONCOLOGY_RESEARCH_TEAM_TEMPLATE)
        self.register(FULLSTACK_MULTIAGENT_TEMPLATE)
        self.register(PHARMA_RESEARCH_COPILOT_TEMPLATE)

    def register(self, template: TemplateDefinition) -> None:
        """Register a template."""
        self._templates[template.id] = template

    def get(self, template_id: ProjectTemplateId) -> TemplateDefinition | None:
        """Get a template by ID."""
        return self._templates.get(template_id)

    def get_all(self) -> list[TemplateDefinition]:
        """Get all registered templates."""
        return list(self._templates.values())

    def list_ids(self) -> list[ProjectTemplateId]:
        """List all template IDs."""
        return list(self._templates.keys())


# Singleton registry instance
_registry: TemplateRegistry | None = None


def get_template_registry() -> TemplateRegistry:
    """Get the template registry singleton."""
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
    return _registry
