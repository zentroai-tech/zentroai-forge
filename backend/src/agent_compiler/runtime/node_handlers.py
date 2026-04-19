"""Node handlers for different node types."""

from typing import Any

from agent_compiler.adapters import get_adapter
from agent_compiler.adapters.base import EngineAdapter
from agent_compiler.config import get_settings
from agent_compiler.models.ir import (
    ErrorParams,
    EngineType,
    JoinParams,
    LLMParams,
    MemoryParams,
    Node,
    NodeType,
    OutputParams,
    ParallelParams,
    RetrieverParams,
    RouterParams,
    ToolParams,
)
from agent_compiler.observability.logging import StepLogger, get_logger
from agent_compiler.runtime.context import ExecutionContext
from agent_compiler.services.tool_security import is_tool_allowed

settings = get_settings()
_logger = get_logger(__name__)


async def handle_llm_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle LLM node execution."""
    params = LLMParams.model_validate(node.params)

    # Get the appropriate adapter
    adapter = get_adapter(
        node_engine=params.engine,
        flow_engine=flow_engine,
        node_type=NodeType.LLM,
    )

    # Render the prompt template
    prompt = context.render_template(params.prompt_template)

    # If conversation history is present (from Chat Playground), incorporate
    # it so the LLM has multi-turn context regardless of the prompt template.
    history = context.user_input.get("history")
    if history and isinstance(history, list):
        history_lines = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            label = "User" if role == "user" else "Assistant"
            history_lines.append(f"{label}: {content}")
        history_text = "\n".join(history_lines)
        prompt = (
            f"Conversation history:\n{history_text}\n\n"
            f"User: {prompt}"
        )

    # If there are retrieved docs, check relevance and inject citations
    if context.retrieved_docs:
        if not context.has_relevant_docs(settings.abstain_threshold):
            # Return abstain response
            return {
                "output": "I don't have enough relevant information to answer this question. Could you please provide more context or rephrase your question?",
                "abstained": True,
                "reason": "No documents above relevance threshold",
            }

        # Inject citations into prompt
        citations = context.get_citations_context()
        prompt = f"Context from retrieved documents:\n{citations}\n\n{prompt}"

    # Build system prompt
    system_prompt = params.system_prompt
    if system_prompt:
        system_prompt = context.render_template(system_prompt)

    # Resolve provider: explicit param > infer from model name
    from agent_compiler.models.ir import LLMProvider

    if params.provider and params.provider != LLMProvider.AUTO:
        llm_provider = params.provider.value  # "openai" | "gemini" | "anthropic"
    else:
        # Legacy fallback: infer from model name
        model_lower = params.model.lower()
        if model_lower.startswith("gemini"):
            llm_provider = "gemini"
        elif model_lower.startswith("claude"):
            llm_provider = "anthropic"
        else:
            llm_provider = "openai"

    api_key = context.get_api_key(llm_provider)
    _logger.info(
        f"LLM node '{node.id}': model={params.model!r}, "
        f"provider={llm_provider}, api_key={'set' if api_key else 'NOT SET'}"
    )

    # Run the LLM
    response = await adapter.run_llm(
        prompt=prompt,
        model=params.model,
        temperature=params.temperature,
        system_prompt=system_prompt,
        max_tokens=params.max_tokens,
        api_key=api_key,
        provider=llm_provider,
    )

    logger.llm_call(params.model, response.tokens_used)

    return {
        "output": response.content,
        "model": response.model,
        "tokens_used": response.tokens_used,
    }


async def handle_retriever_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Retriever node execution."""
    params = RetrieverParams.model_validate(node.params)

    # Get the appropriate adapter (prefers llamaindex for retrievers when auto)
    adapter = get_adapter(
        node_engine=params.engine,
        flow_engine=flow_engine,
        node_type=NodeType.RETRIEVER,
    )

    # Render the query template
    query = context.render_template(params.query_template)

    # Get resolved API key for embeddings (typically OpenAI)
    api_key = context.get_api_key("openai")

    # Retrieve documents
    docs = await adapter.retrieve(
        query=query,
        top_k=params.top_k,
        index_name=params.index_name,
        index_config=params.index_config,
        api_key=api_key,
    )

    # Add to context for downstream nodes
    context.add_retrieved_docs(docs)

    # Calculate average score
    avg_score = sum(d.score for d in docs) / len(docs) if docs else 0.0
    logger.retrieval_results(len(docs), avg_score)

    return {
        "documents": [
            {"content": d.content, "source": d.source, "score": d.score}
            for d in docs
        ],
        "num_documents": len(docs),
        "avg_score": avg_score,
    }


async def handle_tool_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Tool node execution."""
    params = ToolParams.model_validate(node.params)
    if settings.enforce_v1_tool_allowlist:
        if not is_tool_allowed(params.tool_name, settings.v1_tool_allowlist):
            raise RuntimeError(
                f"Tool '{params.tool_name}' is blocked by v1 allowlist. "
                f"Allowed: {settings.v1_tool_allowlist}"
            )

    adapter = get_adapter(
        node_engine=params.engine,
        flow_engine=flow_engine,
        node_type=NodeType.TOOL,
    )

    # Build tool input from context
    tool_input = {
        "input": context.current_value,
        **context.variables,
    }

    # Get resolved API key if tool needs it
    api_key = context.get_api_key("openai")

    result = await adapter.run_tool(
        tool_name=params.tool_name,
        tool_input=tool_input,
        tool_config=params.tool_config,
        api_key=api_key,
        runtime_context=context,
    )

    return {"result": result}


async def handle_router_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Router node execution.

    Supports two modes:
    1. Standard routing: Evaluates conditions against current value
    2. Guard mode: Deterministic routing based on retrieval evidence

    In guard mode, routing is based on:
    - min_docs: Minimum number of retrieved documents
    - min_top_score: Minimum score for the top document
    - else_branch: Branch to take when guard fails (typically 'abstain')
    """
    from agent_compiler.models.ir import RouterGuardMode

    params = RouterParams.model_validate(node.params)

    # Guard mode: deterministic routing based on retrieval evidence
    if params.guard_mode == RouterGuardMode.RETRIEVAL:
        guard_config = params.guard_config

        # Evaluate grounding decision
        decision = context.evaluate_grounding(
            min_docs=guard_config.min_docs,
            min_top_score=guard_config.min_top_score,
        )

        if decision.should_answer:
            # Use default route (typically 'answer' or 'llm')
            selected_route = params.default_route
            logger.info(
                f"Guard passed: {decision.reason}, "
                f"routing to '{selected_route}'"
            )
        else:
            # Use else_branch (typically 'abstain')
            selected_route = guard_config.else_branch
            logger.info(
                f"Guard failed: {decision.reason}, "
                f"routing to '{selected_route}'"
            )

        return {
            "selected_route": selected_route,
            "guard_mode": "retrieval",
            "grounding_decision": {
                "should_answer": decision.should_answer,
                "reason": decision.reason,
                "doc_count": decision.doc_count,
                "top_score": decision.top_score,
                "citations_used": decision.citations_used,
            },
        }

    # Standard mode: condition matching
    current = str(context.current_value).lower() if context.current_value else ""

    # Simple condition matching for MVP
    selected_route = params.default_route

    for condition, target in params.routes.items():
        # Simple substring matching for MVP
        if condition.lower() in current:
            selected_route = target
            break

    return {
        "selected_route": selected_route,
        "condition_matched": selected_route != params.default_route,
    }


async def handle_memory_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Memory node execution.

    For MVP, this is a simple pass-through that stores context.
    """
    params = MemoryParams.model_validate(node.params)

    # Store current context in memory (simplified for MVP)
    memory_entry = {
        "type": params.memory_type,
        "content": str(context.current_value),
        "max_tokens": params.max_tokens,
    }

    return {"memory_stored": memory_entry}


async def handle_output_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Output node execution.

    Supports grounded output formatting with citations when RAG is used.
    If grounding decision indicates abstain, returns abstain response instead.
    """
    params = OutputParams.model_validate(node.params)

    # Check if we should abstain based on grounding decision
    if context.grounding_decision and not context.grounding_decision.should_answer:
        abstain_response = (
            "I don't have enough relevant information to answer this question. "
            "Could you please provide more context or rephrase your question?"
        )
        return {
            "output": abstain_response,
            "format": params.format,
            "abstained": True,
            "abstain_reason": context.grounding_decision.reason,
        }

    # Render output template
    output = context.render_template(params.output_template)

    result: dict[str, Any] = {
        "output": output,
        "format": params.format,
        "abstained": False,
    }

    # Format based on output type
    if params.format == "json":
        try:
            import json
            result["output"] = json.loads(output)
        except json.JSONDecodeError:
            result["output"] = output
            result["format_error"] = "Could not parse as JSON"

    # Include citations if we have a grounding decision with citations
    if context.grounding_decision and context.grounding_decision.citations_used:
        result["citations"] = context.get_structured_citations()
        result["grounded"] = True
        result["grounding_info"] = {
            "doc_count": context.grounding_decision.doc_count,
            "top_score": context.grounding_decision.top_score,
            "citations_used": context.grounding_decision.citations_used,
        }
    elif context.response_citations:
        result["citations"] = context.response_citations
        result["grounded"] = True
    elif context.retrieved_docs:
        # Include all retrieved docs as citations if no grounding decision
        result["citations"] = context.get_structured_citations()
        result["grounded"] = len(context.retrieved_docs) > 0

    return result


async def handle_error_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Error node execution.

    Error nodes are special nodes that handle errors from upstream nodes.
    They receive the error information in context and can format error responses.
    """
    error_info = context.variables.get("_error")

    if error_info:
        return {
            "error_handled": True,
            "error_type": error_info.get("type", "unknown"),
            "error_message": error_info.get("message", "An error occurred"),
            "error_node": error_info.get("node_id"),
            "recovery_attempted": True,
        }

    return {
        "error_handled": False,
        "message": "Error node reached but no error information in context",
    }


async def handle_parallel_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Parallel node execution.

    In MVP DAG execution this marks branch fan-out metadata; downstream branches
    still execute in topological order.
    """
    params = ParallelParams.model_validate(node.params)
    successors = context.variables.get(f"_parallel_successors::{node.id}", [])
    return {
        "output": context.current_value,
        "parallel": {
            "mode": params.mode,
            "branch_count": len(successors) if isinstance(successors, list) else 0,
            "branches": successors if isinstance(successors, list) else [],
        },
    }


async def handle_join_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Handle Join node execution by merging predecessor outputs."""
    params = JoinParams.model_validate(node.params)
    predecessor_ids = context.variables.get(f"_join_predecessors::{node.id}", [])
    if not isinstance(predecessor_ids, list):
        predecessor_ids = []

    predecessor_outputs = [context.get_node_output(pid) for pid in predecessor_ids]

    if params.strategy == "dict":
        merged_output: Any = {
            pid: context.get_node_output(pid)
            for pid in predecessor_ids
        }
    elif params.strategy == "last_non_null":
        merged_output = None
        for item in predecessor_outputs:
            if item is not None:
                merged_output = item
    else:  # array
        merged_output = predecessor_outputs

    return {
        "output": merged_output,
        "joined_from": predecessor_ids,
        "strategy": params.strategy,
    }


# Handler registry
NODE_HANDLERS = {
    NodeType.LLM: handle_llm_node,
    NodeType.RETRIEVER: handle_retriever_node,
    NodeType.TOOL: handle_tool_node,
    NodeType.ROUTER: handle_router_node,
    NodeType.MEMORY: handle_memory_node,
    NodeType.OUTPUT: handle_output_node,
    NodeType.ERROR: handle_error_node,
    NodeType.PARALLEL: handle_parallel_node,
    NodeType.JOIN: handle_join_node,
}


async def execute_node(
    node: Node,
    context: ExecutionContext,
    flow_engine: EngineType,
    logger: StepLogger,
) -> dict[str, Any]:
    """Execute a node based on its type."""
    handler = NODE_HANDLERS.get(node.type)
    if handler is None:
        raise ValueError(f"Unknown node type: {node.type}")

    return await handler(node, context, flow_engine, logger)
