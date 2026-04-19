"""Adapter registry for managing engine adapters."""

from typing import Any

from agent_compiler.adapters.base import EngineAdapter
from agent_compiler.adapters.langchain_adapter import LangChainAdapter
from agent_compiler.adapters.llamaindex_adapter import LlamaIndexAdapter
from agent_compiler.models.ir import EngineType, NodeType
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class AdapterRegistry:
    """Registry for engine adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, EngineAdapter] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default adapters."""
        self._adapters["langchain"] = LangChainAdapter()
        self._adapters["llamaindex"] = LlamaIndexAdapter()

    def register(self, name: str, adapter: EngineAdapter) -> None:
        """Register a custom adapter."""
        self._adapters[name] = adapter

    def get(self, name: str) -> EngineAdapter | None:
        """Get an adapter by name."""
        return self._adapters.get(name)

    def get_available(self) -> list[str]:
        """Get list of available adapter names."""
        return [name for name, adapter in self._adapters.items() if adapter.is_available()]

    def resolve_engine(
        self,
        node_engine: EngineType | None,
        flow_engine: EngineType,
        node_type: NodeType,
    ) -> str:
        """Resolve which engine to use based on preferences and rules.

        Rules:
        1. node.params.engine overrides flow.engine_preference
        2. if "auto": choose "llamaindex" for Retriever nodes by default, otherwise "langchain"
        """
        # Determine preference
        preference = node_engine if node_engine else flow_engine

        if preference == EngineType.AUTO:
            # Auto-selection rules
            if node_type == NodeType.RETRIEVER:
                selected = "llamaindex"
            else:
                selected = "langchain"
        else:
            selected = preference.value

        # Verify availability, fall back if needed
        adapter = self._adapters.get(selected)
        if adapter and adapter.is_available():
            return selected

        # Try fallback
        logger.warning(f"Preferred engine '{selected}' not available, trying fallback")
        for name, adapter in self._adapters.items():
            if adapter.is_available():
                logger.info(f"Using fallback engine: {name}")
                return name

        raise RuntimeError("No engine adapters available. Install langchain or llama-index.")


# Global registry instance
_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry."""
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
    return _registry


def get_adapter(
    node_engine: EngineType | None = None,
    flow_engine: EngineType = EngineType.LANGCHAIN,
    node_type: NodeType = NodeType.LLM,
) -> EngineAdapter:
    """Get an appropriate adapter based on preferences and rules."""
    registry = get_registry()
    engine_name = registry.resolve_engine(node_engine, flow_engine, node_type)
    adapter = registry.get(engine_name)
    if adapter is None:
        raise RuntimeError(f"Engine '{engine_name}' not found in registry")
    return adapter
