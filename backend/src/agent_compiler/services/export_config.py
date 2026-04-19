"""Composable export configuration (engine × surface × packaging).

Presets map to canonical tuples:
  langgraph  → engine=langgraph,  surface=cli,  packaging=local
  runtime    → engine=dispatcher, surface=cli,  packaging=local
  api_server → engine=dispatcher, surface=http, packaging=local
  aws-ecs    → engine=dispatcher, surface=http, packaging=aws-ecs
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExportEngine(str, Enum):
    """Agent execution engine."""

    DISPATCHER = "dispatcher"
    LANGGRAPH = "langgraph"


class ExportSurface(str, Enum):
    """Process surface — how the agent is invoked at runtime."""

    CLI = "cli"
    HTTP = "http"


class ExportPackaging(str, Enum):
    """Deployment packaging / infra target."""

    LOCAL = "local"
    AWS_ECS = "aws-ecs"


# Preset name → (engine, surface, packaging)
_PRESET_MAP: dict[str, tuple[ExportEngine, ExportSurface, ExportPackaging]] = {
    "langgraph":  (ExportEngine.LANGGRAPH,  ExportSurface.CLI,  ExportPackaging.LOCAL),
    "runtime":    (ExportEngine.DISPATCHER, ExportSurface.CLI,  ExportPackaging.LOCAL),
    "api_server": (ExportEngine.DISPATCHER, ExportSurface.HTTP, ExportPackaging.LOCAL),
    "aws-ecs":    (ExportEngine.DISPATCHER, ExportSurface.HTTP, ExportPackaging.AWS_ECS),
}

# Reverse: tuple → preset name (for cache key)
_CACHE_KEY_MAP: dict[tuple[ExportEngine, ExportSurface, ExportPackaging], str] = {
    v: k for k, v in _PRESET_MAP.items()
}

VALID_PRESETS: list[str] = list(_PRESET_MAP)


@dataclass
class ExportConfig:
    """Composable export configuration (engine × surface × packaging).

    Construct via ``from_preset()`` for standard targets or directly for
    advanced combinations (e.g. LangGraph + HTTP + AWS ECS).
    """

    engine: ExportEngine = ExportEngine.DISPATCHER
    surface: ExportSurface = ExportSurface.CLI
    packaging: ExportPackaging = ExportPackaging.LOCAL

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_preset(cls, target: str) -> ExportConfig:
        """Map a legacy preset name to an ExportConfig."""
        if target not in _PRESET_MAP:
            raise ValueError(
                f"Unknown export preset: {target!r}. "
                f"Valid presets: {VALID_PRESETS}"
            )
        engine, surface, packaging = _PRESET_MAP[target]
        return cls(engine=engine, surface=surface, packaging=packaging)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_composition(self) -> None:
        """Raise ValueError for invalid engine × surface × packaging combos."""
        if self.packaging == ExportPackaging.AWS_ECS and self.surface != ExportSurface.HTTP:
            raise ValueError(
                "AWS ECS packaging requires HTTP surface. "
                "Set surface='http' or choose a different packaging target."
            )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def cache_key(self) -> str:
        """Stable cache key for uv.lock files.

        Returns the preset name for standard combos, or a canonical string
        for advanced combinations (so they get their own independent cache).
        """
        return _CACHE_KEY_MAP.get(
            (self.engine, self.surface, self.packaging),
            f"{self.engine.value}-{self.surface.value}-{self.packaging.value}",
        )

    @property
    def label(self) -> str:
        """Human-readable label for display and README generation."""
        if self.packaging == ExportPackaging.AWS_ECS:
            eng = "LangGraph" if self.engine == ExportEngine.LANGGRAPH else "Dispatcher"
            return f"AWS ECS (Fargate) + {eng}"
        if self.surface == ExportSurface.HTTP:
            if self.engine == ExportEngine.LANGGRAPH:
                return "LangGraph + API Server"
            return "API Server"
        if self.engine == ExportEngine.LANGGRAPH:
            return "LangGraph"
        return "Simple Runtime"
