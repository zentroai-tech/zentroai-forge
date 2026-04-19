"""Base protocol for engine adapters."""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class RetrievalResult:
    """Result from a retrieval operation."""

    content: str
    source: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    # Structured citation fields
    doc_id: str | None = None  # Unique document identifier
    chunk_index: int | None = None  # For chunked documents
    title: str | None = None  # Document title
    url: str | None = None  # Source URL if available

    def to_citation(self) -> str:
        """Format as a citation string."""
        parts = []
        if self.doc_id:
            parts.append(f"id={self.doc_id}")
        if self.title:
            parts.append(f"title=\"{self.title}\"")
        parts.append(f"source={self.source}")
        if self.chunk_index is not None:
            parts.append(f"chunk={self.chunk_index}")

        citation_ref = ", ".join(parts)
        return f"[{citation_ref}]\n{self.content}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "title": self.title,
            "url": self.url,
        }


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    model: str
    tokens_used: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class EngineAdapter(Protocol):
    """Protocol for engine adapters (LangChain, LlamaIndex)."""

    @property
    def name(self) -> str:
        """Return the adapter name."""
        ...

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
        """Run an LLM with the given prompt.

        Args:
            prompt: The user prompt
            model: Model name
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            max_tokens: Optional max tokens limit
            api_key: Optional API key (resolved from credentials or env)

        Returns:
            LLMResponse with content and metadata
        """
        ...

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        index_name: str | None = None,
        index_config: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve documents matching the query.

        Args:
            query: Search query
            top_k: Number of results to return
            index_name: Optional index/collection name
            index_config: Optional index configuration
            api_key: Optional API key for embeddings

        Returns:
            List of RetrievalResult
        """
        ...

    async def run_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_config: dict[str, Any] | None = None,
        api_key: str | None = None,
        runtime_context: Any | None = None,
    ) -> dict[str, Any]:
        """Execute a tool and return results.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input data for the tool
            tool_config: Optional tool configuration
            api_key: Optional API key if tool needs it

        Returns:
            Tool execution results
        """
        ...

    def is_available(self) -> bool:
        """Check if this adapter's dependencies are available."""
        ...
