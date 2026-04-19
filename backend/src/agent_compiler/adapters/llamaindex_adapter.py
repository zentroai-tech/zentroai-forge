"""LlamaIndex adapter implementation."""

import os
from typing import Any

from agent_compiler.adapters.base import EngineAdapter, LLMResponse, RetrievalResult
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.encryption_service import mask_secret
from agent_compiler.services.mcp_client import call_mcp_tool, is_mcp_tool
from agent_compiler.services.tool_security import safe_calculator_eval

logger = get_logger(__name__)

# Lazy imports for optional dependencies
_llamaindex_available: bool | None = None


def _check_llamaindex() -> bool:
    """Check if LlamaIndex is available."""
    global _llamaindex_available
    if _llamaindex_available is None:
        try:
            import llama_index  # noqa: F401

            _llamaindex_available = True
        except ImportError:
            _llamaindex_available = False
    return _llamaindex_available


class LlamaIndexAdapter:
    """Adapter for LlamaIndex engine."""

    @property
    def name(self) -> str:
        return "llamaindex"

    def is_available(self) -> bool:
        return _check_llamaindex()

    async def run_llm(
        self,
        prompt: str,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        api_key: str | None = None,
        provider: str | None = None,
    ) -> LLMResponse:
        """Run an LLM using LlamaIndex.

        Args:
            prompt: The user prompt
            model: Model name (default: gpt-3.5-turbo)
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            max_tokens: Optional max tokens
            api_key: Optional API key (falls back to OPENAI_API_KEY env var)

        Returns:
            LLMResponse with content and metadata
        """
        if not self.is_available():
            raise RuntimeError("LlamaIndex is not installed. Install with: pip install llama-index")

        # Resolve API key: explicit param > env var
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY environment variable or configure a credential."
            )

        logger.info(
            f"Running LLM via LlamaIndex: model={model}, temperature={temperature}, "
            f"api_key={mask_secret(resolved_key)}"
        )

        try:
            from llama_index.llms.openai import OpenAI
            from llama_index.core.llms import ChatMessage, MessageRole
        except ImportError:
            # Fallback for older versions
            from llama_index.llms import OpenAI
            from llama_index.llms.base import ChatMessage, MessageRole

        messages = []
        if system_prompt:
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
        messages.append(ChatMessage(role=MessageRole.USER, content=prompt))

        llm = OpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=resolved_key,
        )

        response = await llm.achat(messages)

        return LLMResponse(
            content=response.message.content,
            model=model,
            tokens_used=None,  # LlamaIndex doesn't always expose this
            metadata={"llamaindex_response": True},
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        index_name: str | None = None,
        index_config: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve documents using LlamaIndex.

        Args:
            query: Search query
            top_k: Number of results
            index_name: Optional index name
            index_config: Optional index configuration
            api_key: Optional API key for embeddings

        Returns:
            List of RetrievalResult
        """
        if not self.is_available():
            raise RuntimeError("LlamaIndex is not installed")

        logger.info(f"Retrieving via LlamaIndex: query={query[:50]}..., top_k={top_k}")

        config = index_config or {}

        # For MVP, use a simple vector store index if configured
        if config.get("type") == "vector":
            try:
                from llama_index.core import VectorStoreIndex, StorageContext
                from llama_index.core import load_index_from_storage

                storage_dir = config.get("persist_directory")
                if storage_dir and os.path.exists(storage_dir):
                    storage_context = StorageContext.from_defaults(persist_dir=storage_dir)
                    index = load_index_from_storage(storage_context)
                    retriever = index.as_retriever(similarity_top_k=top_k)
                    nodes = await retriever.aretrieve(query)

                    return [
                        RetrievalResult(
                            content=node.text,
                            source=node.metadata.get("source", "unknown"),
                            score=node.score or 0.0,
                            metadata=node.metadata,
                        )
                        for node in nodes
                    ]
            except Exception as e:
                logger.warning(f"LlamaIndex retrieval failed: {e}")

        # Mock retrieval for MVP when no real index is configured
        logger.warning("Using mock retrieval - no real index configured")
        return [
            RetrievalResult(
                content=f"Mock document for query: {query}",
                source="mock_source",
                score=0.5,
                metadata={"mock": True},
            )
        ]

    async def run_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_config: dict[str, Any] | None = None,
        api_key: str | None = None,
        runtime_context: Any | None = None,
    ) -> dict[str, Any]:
        """Execute a tool using LlamaIndex.

        Args:
            tool_name: Name of the tool
            tool_input: Input data for the tool
            tool_config: Optional tool configuration
            api_key: Optional API key if tool needs it

        Returns:
            Tool execution results
        """
        if not self.is_available():
            raise RuntimeError("LlamaIndex is not installed")

        logger.info(f"Running tool via LlamaIndex: {tool_name}")
        if is_mcp_tool(tool_name, tool_config):
            session_cache = getattr(runtime_context, "mcp_sessions", None)
            return await call_mcp_tool(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_config=tool_config,
                session_cache=session_cache,
            )

        # LlamaIndex tool support
        if tool_name == "query_engine":
            # Placeholder for query engine tool
            return {"result": f"Query results for: {tool_input.get('query', '')}", "mock": True}
        if tool_name == "calculator":
            expression = str(tool_input.get("expression", "")).strip()
            if not expression:
                return {"error": "Missing required field: expression"}
            try:
                return {"result": safe_calculator_eval(expression)}
            except Exception as e:
                return {"error": str(e)}
        if tool_name in {"datetime", "now"}:
            from datetime import datetime, timezone

            return {"result": datetime.now(timezone.utc).isoformat()}
        else:
            return {
                "tool_name": tool_name,
                "input": tool_input,
                "result": "Tool execution not implemented",
                "mock": True,
            }


# Ensure the adapter conforms to the protocol
def _check_protocol() -> None:
    adapter: EngineAdapter = LlamaIndexAdapter()
    assert adapter is not None
