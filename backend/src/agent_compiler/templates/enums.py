"""Enums for Project Templates.

Defines the supported templates and target engines.
"""

from enum import Enum


class ProjectTemplateId(str, Enum):
    """Supported project templates.

    Each template provides a pre-configured graph structure
    optimized for specific use cases.
    """

    BLANK = "blank"
    SIMPLE_AGENT = "simple_agent"
    RAG_AGENT = "rag_agent"
    SUPERVISOR_WORKERS = "supervisor_workers"
    ONCOLOGY_RESEARCH_TEAM = "oncology_research_team"
    FULLSTACK_MULTIAGENT = "fullstack_multiagent"
    PHARMA_RESEARCH_COPILOT = "pharma_research_copilot"


class TargetEngine(str, Enum):
    """Target execution engines for project templates.

    Determines the runtime backend for the generated IR.
    """

    LLAMAINDEX = "llamaindex"
    LANGGRAPH = "langgraph"  # LangGraph/LangChain bucket

    @classmethod
    def default(cls) -> "TargetEngine":
        """Return the default engine."""
        return cls.LANGGRAPH


# Template version constants for migration tracking
TEMPLATE_VERSIONS: dict[ProjectTemplateId, str] = {
    ProjectTemplateId.BLANK: "1.0.0",
    ProjectTemplateId.SIMPLE_AGENT: "1.0.0",
    ProjectTemplateId.RAG_AGENT: "1.0.0",
    ProjectTemplateId.SUPERVISOR_WORKERS: "1.0.0",
    ProjectTemplateId.ONCOLOGY_RESEARCH_TEAM: "1.0.0",
    ProjectTemplateId.FULLSTACK_MULTIAGENT: "1.0.0",
    ProjectTemplateId.PHARMA_RESEARCH_COPILOT: "1.0.0",
}


def get_template_version(template_id: ProjectTemplateId) -> str:
    """Get the current version of a template."""
    return TEMPLATE_VERSIONS.get(template_id, "1.0.0")
