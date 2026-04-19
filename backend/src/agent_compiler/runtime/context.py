"""Execution context for flow runs."""

from dataclasses import dataclass, field
from typing import Any

from agent_compiler.adapters.base import RetrievalResult


@dataclass
class GroundingDecision:
    """Result of a grounding decision (abstain vs answer)."""

    should_answer: bool
    reason: str
    doc_count: int = 0
    top_score: float = 0.0
    citations_used: list[str] = field(default_factory=list)


@dataclass
class ExecutionContext:
    """Context passed through flow execution.

    Maintains state and artifacts as nodes are executed.
    """

    # Original user input
    user_input: dict[str, Any] = field(default_factory=dict)

    # Node outputs indexed by node_id
    node_outputs: dict[str, Any] = field(default_factory=dict)

    # Retrieved documents with citations (for RAG)
    retrieved_docs: list[RetrievalResult] = field(default_factory=list)

    # Current working value (passed between nodes)
    current_value: Any = None

    # Variables that can be referenced in templates
    variables: dict[str, Any] = field(default_factory=dict)

    # Metadata accumulated during execution
    metadata: dict[str, Any] = field(default_factory=dict)

    # Grounding decision (set by Router guard or LLM node)
    grounding_decision: GroundingDecision | None = None

    # Citations used in the final response
    response_citations: list[dict[str, Any]] = field(default_factory=list)

    # Resolved credentials by provider (populated at run start)
    # Keys: "openai", "anthropic", "gemini" -> Values: API keys
    # SECURITY: These are never serialized or logged
    resolved_credentials: dict[str, str] = field(default_factory=dict)

    # Environment variables loaded from flow_env_vars for the active profile
    # Keys: variable name (e.g. "MY_VAR") -> Values: variable value
    env_vars: dict[str, str] = field(default_factory=dict)

    # Multi-agent: current agent ID (set by AgentExecutor)
    agent_id: str | None = None

    # Multi-agent: namespace-scoped memory shared between agents
    # Keys: namespace -> {key: value}
    agent_memory: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Reused MCP stdio sessions for this run.
    # Keys: deterministic session key -> MCPStdioSession-like object with async close().
    mcp_sessions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize current_value from user input if present."""
        if "input" in self.user_input and self.current_value is None:
            self.current_value = self.user_input["input"]

    def get_agent_memory(self, namespace: str) -> dict[str, Any]:
        """Get the memory dict for an agent namespace.

        Args:
            namespace: The memory namespace

        Returns:
            Dictionary of stored values for this namespace
        """
        return self.agent_memory.setdefault(namespace, {})

    def set_agent_memory(self, namespace: str, key: str, value: Any) -> None:
        """Set a value in an agent's memory namespace.

        Args:
            namespace: The memory namespace
            key: The key to set
            value: The value to store
        """
        self.agent_memory.setdefault(namespace, {})[key] = value

    def get_api_key(self, provider: str) -> str | None:
        """Get resolved API key for a provider.

        Args:
            provider: Provider name ("openai", "anthropic", "gemini")

        Returns:
            API key if resolved, None otherwise
        """
        return self.resolved_credentials.get(provider.lower())

    def set_node_output(self, node_id: str, output: Any) -> None:
        """Store output from a node.

        The full output (including metadata like model, tokens, etc.) is stored
        in ``node_outputs`` so it can be inspected later. However,
        ``current_value`` — which is what ``{current}`` resolves to in templates
        — is set to just the meaningful text/value so downstream nodes receive
        clean data instead of a raw metadata dict.
        """
        self.node_outputs[node_id] = output
        # Extract the meaningful value for current_value so templates get
        # clean text instead of the full metadata dict.
        if isinstance(output, dict) and "output" in output:
            self.current_value = output["output"]
        else:
            self.current_value = output

    def get_node_output(self, node_id: str) -> Any:
        """Get output from a specific node."""
        return self.node_outputs.get(node_id)

    def add_retrieved_docs(self, docs: list[RetrievalResult]) -> None:
        """Add retrieved documents to context."""
        self.retrieved_docs.extend(docs)

    def get_citations_context(self) -> str:
        """Get formatted citations for LLM prompts."""
        if not self.retrieved_docs:
            return ""

        citations = []
        for i, doc in enumerate(self.retrieved_docs, 1):
            citations.append(f"[{i}] {doc.to_citation()}")

        return "\n\n".join(citations)

    def has_relevant_docs(self, threshold: float = 0.3) -> bool:
        """Check if there are documents above the relevance threshold."""
        if not self.retrieved_docs:
            return False
        return any(doc.score >= threshold for doc in self.retrieved_docs)

    def evaluate_grounding(
        self,
        min_docs: int = 1,
        min_top_score: float = 0.3,
    ) -> GroundingDecision:
        """Evaluate grounding based on retrieval evidence.

        This is a deterministic decision based on document count and scores.

        Args:
            min_docs: Minimum number of documents required
            min_top_score: Minimum score for the top document

        Returns:
            GroundingDecision with the result
        """
        doc_count = len(self.retrieved_docs)
        top_score = max((d.score for d in self.retrieved_docs), default=0.0)

        # Deterministic grounding decision
        if doc_count < min_docs:
            decision = GroundingDecision(
                should_answer=False,
                reason=f"Insufficient documents: {doc_count} < {min_docs}",
                doc_count=doc_count,
                top_score=top_score,
            )
        elif top_score < min_top_score:
            decision = GroundingDecision(
                should_answer=False,
                reason=f"Top score too low: {top_score:.3f} < {min_top_score}",
                doc_count=doc_count,
                top_score=top_score,
            )
        else:
            # Collect citation IDs from docs above threshold
            citations_used = [
                d.doc_id or d.source
                for d in self.retrieved_docs
                if d.score >= min_top_score
            ]
            decision = GroundingDecision(
                should_answer=True,
                reason=f"Grounded with {len(citations_used)} relevant document(s)",
                doc_count=doc_count,
                top_score=top_score,
                citations_used=citations_used,
            )

        self.grounding_decision = decision
        return decision

    def get_structured_citations(self) -> list[dict[str, Any]]:
        """Get citations in structured format for response."""
        return [doc.to_dict() for doc in self.retrieved_docs]

    def mark_citations_used(self, doc_ids: list[str]) -> None:
        """Mark specific citations as used in the response."""
        self.response_citations = [
            doc.to_dict()
            for doc in self.retrieved_docs
            if (doc.doc_id or doc.source) in doc_ids
        ]

    def render_template(self, template: str) -> str:
        """Render a template string with context variables.

        Available variables:
        - {input}: The original user input
        - {current}: The current working value
        - {history}: Formatted conversation history (from Chat Playground)
        - {citations}: Formatted citations from retrieved docs
        - {node.<node_id>}: Output from a specific node
        - Any custom variables set in self.variables
        """
        # Format conversation history if present
        history_text = ""
        raw_history = self.user_input.get("history")
        if raw_history and isinstance(raw_history, list):
            lines = []
            for msg in raw_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                label = "User" if role == "user" else "Assistant"
                lines.append(f"{label}: {content}")
            history_text = "\n".join(lines)

        context = {
            "input": self.user_input.get("input", ""),
            "current": str(self.current_value) if self.current_value else "",
            "history": history_text,
            "citations": self.get_citations_context(),
            **self.variables,
        }

        # Add node outputs with "node." prefix — extract meaningful text
        for node_id, output in self.node_outputs.items():
            if isinstance(output, dict) and "output" in output:
                context[f"node.{node_id}"] = str(output["output"]) if output["output"] else ""
            else:
                context[f"node.{node_id}"] = str(output) if output else ""

        # Add environment variables with "env." prefix
        for var_name, var_value in self.env_vars.items():
            context[f"env.{var_name}"] = var_value

        # Simple template substitution
        result = template
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value))

        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization.

        SECURITY: Credentials are NEVER included in serialization.
        """
        result = {
            "user_input": self.user_input,
            "node_outputs": {
                k: str(v) if not isinstance(v, (dict, list, str, int, float, bool, type(None))) else v
                for k, v in self.node_outputs.items()
            },
            "retrieved_docs": [doc.to_dict() for doc in self.retrieved_docs],
            "current_value": str(self.current_value) if self.current_value else None,
            "variables": self.variables,
            "metadata": self.metadata,
            # SECURITY: resolved_credentials is intentionally excluded
        }

        # Include grounding decision if present
        if self.grounding_decision:
            result["grounding"] = {
                "should_answer": self.grounding_decision.should_answer,
                "reason": self.grounding_decision.reason,
                "doc_count": self.grounding_decision.doc_count,
                "top_score": self.grounding_decision.top_score,
                "citations_used": self.grounding_decision.citations_used,
            }

        # Include response citations if present
        if self.response_citations:
            result["citations"] = self.response_citations

        return result

    async def close_external_resources(self) -> None:
        """Close pooled external runtime resources (e.g., MCP sessions)."""
        for key, session in list(self.mcp_sessions.items()):
            close = getattr(session, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    # Best effort cleanup; execution should not fail on close.
                    pass
            self.mcp_sessions.pop(key, None)
