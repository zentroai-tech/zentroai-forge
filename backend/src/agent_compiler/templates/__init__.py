"""Project Templates module for Zentro Forge.

Provides template-based project creation with engine-specific IR generation.
"""

from agent_compiler.templates.enums import ProjectTemplateId, TargetEngine
from agent_compiler.templates.factory import TemplateFactory
from agent_compiler.templates.registry import (
    get_template_registry,
    TemplateRegistry,
    TemplateDefinition,
    TemplateTag,
)

__all__ = [
    "ProjectTemplateId",
    "TargetEngine",
    "TemplateFactory",
    "TemplateRegistry",
    "TemplateDefinition",
    "TemplateTag",
    "get_template_registry",
]
