"""Services package.

Avoid eager imports here to prevent circular dependencies during runtime boot.
Use lazy attribute loading for compatibility with previous import style:
`from agent_compiler.services import FlowService`.
"""

from __future__ import annotations

from typing import Any

__all__ = ["FlowService", "RunService", "ExportService", "PreviewService"]


def __getattr__(name: str) -> Any:
    if name == "FlowService":
        from agent_compiler.services.flow_service import FlowService

        return FlowService
    if name == "RunService":
        from agent_compiler.services.run_service import RunService

        return RunService
    if name == "ExportService":
        from agent_compiler.services.export_service import ExportService

        return ExportService
    if name == "PreviewService":
        from agent_compiler.services.preview_service import PreviewService

        return PreviewService
    raise AttributeError(name)
