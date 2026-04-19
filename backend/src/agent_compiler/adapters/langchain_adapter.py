"""LangChain adapter implementation.

Supports OpenAI and Gemini providers via a provider-aware model factory.
Provider is inferred from the model name (gemini* → Gemini, else → OpenAI)
or can be set explicitly.
"""

import os
from typing import Any

from agent_compiler.adapters.base import EngineAdapter, LLMResponse, RetrievalResult
from agent_compiler.services.mcp_client import call_mcp_tool, is_mcp_tool
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.encryption_service import mask_secret
from agent_compiler.services.tool_security import safe_calculator_eval

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
#  Lazy availability check
# ---------------------------------------------------------------------------

_langchain_available: bool | None = None


def _check_langchain() -> bool:
    """Check if LangChain is available."""
    global _langchain_available
    if _langchain_available is None:
        try:
            import langchain  # noqa: F401

            _langchain_available = True
        except ImportError:
            _langchain_available = False
    return _langchain_available


# ---------------------------------------------------------------------------
#  Provider-aware model factory
# ---------------------------------------------------------------------------

def _infer_provider(model: str) -> str:
    """Infer LLM provider from the model name.

    Returns ``"gemini"`` when *model* starts with ``gemini`` (case-insensitive),
    otherwise ``"openai"``.
    """
    return "gemini" if model.lower().startswith("gemini") else "openai"


def _import_messages() -> tuple[type, type]:
    """Import HumanMessage / SystemMessage with legacy fallback.

    Both OpenAI and Gemini LC integrations use the same message types.
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        from langchain.schema import HumanMessage, SystemMessage  # type: ignore[no-redef]
    return HumanMessage, SystemMessage


def build_chat_model(
    *,
    provider: str | None = None,
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    timeout_s: int | None = None,
) -> Any:
    """Construct a LangChain chat model for the requested provider.

    Parameters
    ----------
    provider:
        ``"openai"`` or ``"gemini"``.  When *None* the provider is inferred
        from *model* (``gemini*`` → Gemini, else → OpenAI).
    model:
        Model identifier, e.g. ``"gpt-4o"`` or ``"gemini-1.5-pro"``.
    temperature:
        Sampling temperature.
    max_tokens:
        Maximum output tokens (maps to ``max_output_tokens`` for Gemini).
    api_key:
        Explicit API key.  When *None* falls back to the env var.
    api_key_env:
        Override for the environment variable name that holds the API key.
    timeout_s:
        Request timeout in seconds.

    Returns
    -------
    A LangChain ``BaseChatModel`` instance ready for ``.ainvoke()``.

    Raises
    ------
    RuntimeError
        If the required package is missing or the API key is not set.
    """
    if provider is None:
        provider = _infer_provider(model)

    if provider == "gemini":
        return _build_gemini(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            api_key_env=api_key_env,
            timeout_s=timeout_s,
        )

    # Default: OpenAI
    return _build_openai(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
        api_key_env=api_key_env,
        timeout_s=timeout_s,
    )


# -- private builders -------------------------------------------------------


def _build_openai(
    *,
    model: str,
    temperature: float,
    max_tokens: int | None,
    api_key: str | None,
    api_key_env: str | None,
    timeout_s: int | None,
) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        try:
            from langchain.chat_models import ChatOpenAI  # type: ignore[no-redef]
        except ImportError:
            raise RuntimeError(
                "OpenAI provider selected but langchain-openai is not installed. "
                "Install with:  pip install langchain-openai"
            )

    env_var = api_key_env or "OPENAI_API_KEY"
    resolved_key = api_key or os.environ.get(env_var)
    if not resolved_key:
        raise RuntimeError(
            f"OpenAI provider selected (model={model!r}) but API key not found. "
            f"Set the {env_var} environment variable or configure a credential. "
            f"If you intended to use Gemini, make sure the node's model name "
            f"starts with 'gemini' and save the flow before running."
        )

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "api_key": resolved_key,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if timeout_s is not None:
        kwargs["request_timeout"] = timeout_s
    return ChatOpenAI(**kwargs)


def _build_gemini(
    *,
    model: str,
    temperature: float,
    max_tokens: int | None,
    api_key: str | None,
    api_key_env: str | None,
    timeout_s: int | None,
) -> Any:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        raise RuntimeError(
            "Gemini provider selected but langchain-google-genai is not installed. "
            "Install with:  pip install langchain-google-genai"
        )

    env_var = api_key_env or "GOOGLE_API_KEY"
    resolved_key = api_key or os.environ.get(env_var)
    if not resolved_key:
        raise RuntimeError(
            f"Gemini provider selected but API key not found. "
            f"Set the {env_var} environment variable or configure a credential."
        )

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "google_api_key": resolved_key,
    }
    if max_tokens is not None:
        kwargs["max_output_tokens"] = max_tokens
    if timeout_s is not None:
        kwargs["timeout"] = timeout_s
    return ChatGoogleGenerativeAI(**kwargs)


# ---------------------------------------------------------------------------
#  Adapter
# ---------------------------------------------------------------------------


class LangChainAdapter:
    """Adapter for LangChain engine — supports OpenAI & Gemini."""

    @property
    def name(self) -> str:
        return "langchain"

    def is_available(self) -> bool:
        return _check_langchain()

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
        """Run an LLM using LangChain.

        Args:
            prompt: The user prompt
            model: Model name (e.g. ``gpt-4o``, ``gemini-1.5-pro``)
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            max_tokens: Optional max tokens
            api_key: Optional API key (falls back to env var for the provider)
            provider: Explicit provider (``"openai"``, ``"gemini"``, ``"anthropic"``).
                      If None, inferred from model name.

        Returns:
            LLMResponse with content and metadata
        """
        if not self.is_available():
            raise RuntimeError(
                "LangChain is not installed. "
                "Install with: pip install langchain langchain-openai"
            )

        resolved_provider = provider or _infer_provider(model)

        # Resolve API key: explicit param > env var
        if api_key:
            resolved_key = api_key
        else:
            env_var = "GOOGLE_API_KEY" if resolved_provider == "gemini" else "OPENAI_API_KEY"
            resolved_key = os.environ.get(env_var, "")

        # Log with masked key for debugging (never log full key)
        logger.info(
            "Running LLM via LangChain: provider=%s model=%s temperature=%s api_key=%s",
            resolved_provider,
            model,
            temperature,
            mask_secret(resolved_key) if resolved_key else "<not set>",
        )

        # Build provider-specific model (validates key + imports inside)
        llm = build_chat_model(
            provider=resolved_provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
        )

        # Messages — same import for both providers
        HumanMessage, SystemMessage = _import_messages()
        messages: list[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        response = await llm.ainvoke(messages)

        tokens_used = None
        if hasattr(response, "response_metadata") and response.response_metadata:
            meta = response.response_metadata
            # LangChain/OpenAI often use "usage", others "token_usage"
            usage = meta.get("token_usage") or meta.get("usage") or {}
            if isinstance(usage, dict):
                total = usage.get("total_tokens")
                if total is None and (usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None):
                    total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
                tokens_used = int(total) if total is not None else None
            elif isinstance(usage, (int, float)):
                tokens_used = int(usage)

        return LLMResponse(
            content=response.content,
            model=model,
            tokens_used=tokens_used,
            metadata={"langchain_response": True, "provider": provider},
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        index_name: str | None = None,
        index_config: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve documents using LangChain.

        Args:
            query: Search query
            top_k: Number of results
            index_name: Optional index/collection name
            index_config: Optional index configuration
            api_key: Optional API key for embeddings

        Returns:
            List of RetrievalResult
        """
        if not self.is_available():
            raise RuntimeError("LangChain is not installed")

        logger.info("Retrieving via LangChain: query=%s..., top_k=%s", query[:50], top_k)

        config = index_config or {}

        # Resolve API key for embeddings
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")

        # For MVP, use a simple in-memory vector store if no index provided
        # In production, this would connect to a real vector store
        if config.get("type") == "chroma" and resolved_key:
            try:
                from langchain_community.vectorstores import Chroma
                from langchain_openai import OpenAIEmbeddings

                embeddings = OpenAIEmbeddings(api_key=resolved_key)
                vectorstore = Chroma(
                    collection_name=index_name or "default",
                    embedding_function=embeddings,
                    persist_directory=config.get("persist_directory"),
                )
                docs = vectorstore.similarity_search_with_score(query, k=top_k)

                return [
                    RetrievalResult(
                        content=doc.page_content,
                        source=doc.metadata.get("source", "unknown"),
                        score=1 - score,  # Convert distance to similarity
                        metadata=doc.metadata,
                    )
                    for doc, score in docs
                ]
            except Exception as e:
                logger.warning("Chroma retrieval failed: %s", e)

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
        """Execute a tool using LangChain.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input data for the tool
            tool_config: Optional tool configuration
            api_key: Optional API key if tool needs it

        Returns:
            Tool execution results
        """
        if not self.is_available():
            raise RuntimeError("LangChain is not installed")

        logger.info("Running tool via LangChain: %s", tool_name)

        # Built-in tools support
        config = tool_config or {}
        if is_mcp_tool(tool_name, config):
            session_cache = getattr(runtime_context, "mcp_sessions", None)
            return await call_mcp_tool(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_config=config,
                session_cache=session_cache,
            )

        if tool_name == "search":
            # Placeholder for web search tool
            return {"result": f"Search results for: {tool_input.get('query', '')}", "mock": True}
        elif tool_name == "calculator":
            try:
                expression = str(tool_input.get("expression", "")).strip()
                if not expression:
                    return {"error": "Missing required field: expression"}
                result = safe_calculator_eval(expression)
                return {"result": result}
            except Exception as e:
                return {"error": str(e)}
        elif tool_name in {"datetime", "now"}:
            from datetime import datetime, timezone

            return {"result": datetime.now(timezone.utc).isoformat()}
        else:
            # Generic tool handling
            return {
                "tool_name": tool_name,
                "input": tool_input,
                "result": "Tool execution not implemented",
                "mock": True,
            }


# Ensure the adapter conforms to the protocol
def _check_protocol() -> None:
    adapter: EngineAdapter = LangChainAdapter()
    assert adapter is not None
