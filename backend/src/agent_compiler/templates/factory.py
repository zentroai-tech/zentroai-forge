"""Template Factory for generating IR from templates.

Provides deterministic IR generation based on template ID, engine, and parameters.
"""

import hashlib
import json
from typing import Any

from agent_compiler.models.ir import (
    Edge,
    EngineType,
    FallbackSpec,
    Flow,
    LLMProvider,
    Node,
    NodeType,
    RetrySpec,
)
from agent_compiler.models.ir_v2 import (
    AbstainSpec,
    AgentSpec,
    BudgetSpec,
    EntrypointSpec,
    FlowIRv2,
    GraphSpec,
    HandoffMode,
    HandoffRule,
    LlmBinding,
    PolicySpec,
    RedactionSpec,
    ResourceRegistry,
    SanitizationSpec,
)
from agent_compiler.templates.enums import ProjectTemplateId, TargetEngine, get_template_version
from agent_compiler.templates.registry import get_template_registry
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class TemplateValidationError(Exception):
    """Raised when template validation fails."""

    pass


class TemplateFactory:
    """Factory for creating IR from project templates.

    Generates deterministic, engine-specific IR structures based on
    template definitions and user parameters.
    """

    @staticmethod
    def create_ir(
        template_id: ProjectTemplateId,
        engine: TargetEngine,
        project_id: str,
        project_name: str,
        params: dict[str, Any] | None = None,
    ) -> FlowIRv2:
        """Create IR from a template.

        Args:
            template_id: The template to use
            engine: Target execution engine
            project_id: Unique project identifier
            project_name: Human-readable project name
            params: Optional template-specific parameters

        Returns:
            Complete FlowIRv2 structure

        Raises:
            TemplateValidationError: If template/engine combination is invalid
        """
        params = params or {}

        # Validate template exists
        registry = get_template_registry()
        template_def = registry.get(template_id)
        if template_def is None:
            raise TemplateValidationError(f"Unknown template: {template_id}")

        # Validate engine is supported
        if not template_def.supports_engine(engine):
            raise TemplateValidationError(
                f"Template '{template_id.value}' does not support engine '{engine.value}'. "
                f"Supported: {[e.value for e in template_def.supported_engines]}"
            )

        # Apply default params
        resolved_params = TemplateFactory._resolve_params(template_def, params)

        # Generate IR based on template
        if template_id == ProjectTemplateId.BLANK:
            return TemplateFactory._create_blank_ir(
                project_id, project_name, engine, resolved_params
            )
        elif template_id == ProjectTemplateId.SIMPLE_AGENT:
            return TemplateFactory._create_simple_agent_ir(
                project_id, project_name, engine, resolved_params
            )
        elif template_id == ProjectTemplateId.RAG_AGENT:
            return TemplateFactory._create_rag_agent_ir(
                project_id, project_name, engine, resolved_params
            )
        elif template_id == ProjectTemplateId.SUPERVISOR_WORKERS:
            return TemplateFactory._create_supervisor_workers_ir(
                project_id, project_name, engine, resolved_params
            )
        elif template_id == ProjectTemplateId.ONCOLOGY_RESEARCH_TEAM:
            return TemplateFactory._create_oncology_research_team_ir(
                project_id, project_name, engine, resolved_params
            )
        elif template_id == ProjectTemplateId.FULLSTACK_MULTIAGENT:
            return TemplateFactory._create_fullstack_multiagent_ir(
                project_id, project_name, engine, resolved_params
            )
        elif template_id == ProjectTemplateId.PHARMA_RESEARCH_COPILOT:
            return TemplateFactory._create_pharma_research_copilot_ir(
                project_id, project_name, engine, resolved_params
            )
        else:
            raise TemplateValidationError(f"No generator for template: {template_id}")

    @staticmethod
    def _resolve_params(template_def: Any, user_params: dict[str, Any]) -> dict[str, Any]:
        """Resolve parameters with defaults."""
        resolved: dict[str, Any] = {}

        for param in template_def.params:
            if param.name in user_params:
                resolved[param.name] = user_params[param.name]
            else:
                resolved[param.name] = param.default

        return resolved

    @staticmethod
    def _engine_to_engine_type(engine: TargetEngine) -> EngineType:
        """Convert TargetEngine to EngineType."""
        if engine == TargetEngine.LLAMAINDEX:
            return EngineType.LLAMAINDEX
        return EngineType.LANGCHAIN

    @staticmethod
    def _create_single_agent_ir_v2(
        *,
        project_id: str,
        project_name: str,
        engine_type: EngineType,
        description: str,
        nodes: list[Node],
        edges: list[Edge],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        system_prompt: str | None = None,
        agent_id: str = "main",
        agent_name: str = "Main Agent",
    ) -> FlowIRv2:
        start_node = next(
            (n for n in nodes if bool((n.params or {}).get("is_start"))),
            nodes[0],
        )
        return FlowIRv2(
            ir_version="2",
            flow=Flow(
                id=project_id,
                name=project_name,
                version="1.0.0",
                engine_preference=engine_type,
                description=description,
            ),
            agents=[
                AgentSpec(
                    id=agent_id,
                    name=agent_name,
                    graph=GraphSpec(
                        nodes=nodes,
                        edges=edges,
                        root=start_node.id,
                    ),
                    llm=LlmBinding(
                        provider=LLMProvider.AUTO,
                        model=model,
                        temperature=temperature,
                        system_prompt=system_prompt,
                    ),
                    tools_allowlist=[],
                    memory_namespace=f"{agent_id}_memory",
                    budgets=BudgetSpec(max_depth=5),
                )
            ],
            entrypoints=[EntrypointSpec(name="main", agent_id=agent_id)],
            handoffs=[],
            resources=ResourceRegistry(shared_memory_namespaces=[], global_tools=[]),
        )

    # =========================================================================
    # Blank Template
    # =========================================================================

    @staticmethod
    def _create_blank_ir(
        project_id: str,
        project_name: str,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> FlowIRv2:
        """Create IR for blank template.

        Minimal IR with just an output node as placeholder.
        """
        engine_type = TemplateFactory._engine_to_engine_type(engine)

        nodes = [
            Node(
                id="output",
                type=NodeType.OUTPUT,
                name="Output",
                params={
                    "output_template": "{input}",
                    "format": "text",
                    "is_start": True,
                },
            )
        ]
        return TemplateFactory._create_single_agent_ir_v2(
            project_id=project_id,
            project_name=project_name,
            engine_type=engine_type,
            description="Blank project - add your nodes here",
            nodes=nodes,
            edges=[],
            model="gpt-4o-mini",
            temperature=0.7,
            system_prompt=None,
        )

    # =========================================================================
    # Simple Agent Template
    # =========================================================================

    @staticmethod
    def _create_simple_agent_ir(
        project_id: str,
        project_name: str,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> FlowIRv2:
        """Create IR for simple agent template.

        Structure:
        - Input (LLM for processing) -> Router -> [Tool Executor | Direct Response]
        - Optional Memory node
        - Output formatting

        Engine-specific variations:
        - LangGraph: Uses LangGraph state machine primitives
        - LlamaIndex: Uses LlamaIndex agent runner primitives
        """
        engine_type = TemplateFactory._engine_to_engine_type(engine)
        include_memory = params.get("include_memory", True)
        model = params.get("model", "gpt-4o-mini")
        tools = params.get("tools", "basic")

        nodes: list[Node] = []
        edges: list[Edge] = []

        # Node 1: Input processor (LLM)
        input_system_prompt = TemplateFactory._get_agent_system_prompt(engine, tools)
        nodes.append(
            Node(
                id="input_processor",
                type=NodeType.LLM,
                name="Input Processor",
                params={
                    "model": model,
                    "temperature": 0.7,
                    "system_prompt": input_system_prompt,
                    "prompt_template": "{input}",
                    "engine": engine_type.value,
                    "is_start": True,
                },
            )
        )

        # Node 2: Memory (optional)
        if include_memory:
            nodes.append(
                Node(
                    id="memory",
                    type=NodeType.MEMORY,
                    name="Conversation Memory",
                    params={
                        "memory_type": "buffer",
                        "max_tokens": 4000,
                        "engine": engine_type.value,
                    },
                )
            )
            edges.append(Edge(source="input_processor", target="memory"))

        # Node 3: Router for tool use decision
        router_source = "memory" if include_memory else "input_processor"
        nodes.append(
            Node(
                id="router",
                type=NodeType.ROUTER,
                name="Action Router",
                params={
                    "routes": {
                        "tool_call": "tool_executor",
                        "direct": "response_generator",
                    },
                    "default_route": "response_generator",
                    "engine": engine_type.value,
                },
            )
        )
        edges.append(Edge(source=router_source, target="router"))

        # Node 4: Tool executor
        if tools != "none":
            tool_config = TemplateFactory._get_tool_config(tools, engine)
            nodes.append(
                Node(
                    id="tool_executor",
                    type=NodeType.TOOL,
                    name="Tool Executor",
                    params={
                        "tool_name": "agent_tools",
                        "tool_config": tool_config,
                        "engine": engine_type.value,
                    },
                )
            )
            edges.append(
                Edge(source="router", target="tool_executor", condition="tool_call")
            )
            edges.append(Edge(source="tool_executor", target="response_generator"))

        # Node 5: Response generator (LLM)
        nodes.append(
            Node(
                id="response_generator",
                type=NodeType.LLM,
                name="Response Generator",
                params={
                    "model": model,
                    "temperature": 0.7,
                    "system_prompt": "Generate a helpful response based on the conversation context.",
                    "prompt_template": "{current}",
                    "engine": engine_type.value,
                },
            )
        )
        edges.append(
            Edge(source="router", target="response_generator", condition="direct")
        )

        # Node 6: Output
        nodes.append(
            Node(
                id="output",
                type=NodeType.OUTPUT,
                name="Output",
                params={
                    "output_template": "{current}",
                    "format": "text",
                },
            )
        )
        edges.append(Edge(source="response_generator", target="output"))

        description = f"Simple agent with {'memory, ' if include_memory else ''}{tools} tools"

        return TemplateFactory._create_single_agent_ir_v2(
            project_id=project_id,
            project_name=project_name,
            engine_type=engine_type,
            description=description,
            nodes=nodes,
            edges=edges,
            model=model,
            temperature=0.7,
            system_prompt=TemplateFactory._get_agent_system_prompt(engine, tools),
        )

    @staticmethod
    def _get_agent_system_prompt(engine: TargetEngine, tools: str) -> str:
        """Get engine-specific system prompt for agent."""
        base_prompt = (
            "You are a helpful AI assistant. Analyze the user's request and determine "
            "the best course of action."
        )

        if tools != "none":
            base_prompt += (
                " If the request requires using tools, indicate 'tool_call' in your response. "
                "Otherwise, respond directly."
            )

        if engine == TargetEngine.LANGGRAPH:
            base_prompt += "\n\nYou are running on LangGraph. Use structured outputs when possible."
        else:
            base_prompt += "\n\nYou are running on LlamaIndex. Leverage the agent framework capabilities."

        return base_prompt

    @staticmethod
    def _get_tool_config(tools: str, engine: TargetEngine) -> dict[str, Any]:
        """Get tool configuration based on preset and engine."""
        configs: dict[str, dict[str, Any]] = {
            "basic": {
                "enabled_tools": ["calculator", "datetime"],
                "max_retries": 2,
            },
            "web_search": {
                "enabled_tools": ["web_search", "url_reader"],
                "max_retries": 3,
            },
            "code_interpreter": {
                "enabled_tools": ["python_repl", "file_reader"],
                "max_retries": 2,
                "sandbox": True,
            },
        }

        config = configs.get(tools, configs["basic"])

        # Engine-specific adjustments
        if engine == TargetEngine.LANGGRAPH:
            config["framework"] = "langgraph"
            config["tool_calling_method"] = "function_calling"
        else:
            config["framework"] = "llamaindex"
            config["tool_calling_method"] = "react"

        return config

    # =========================================================================
    # RAG Agent Template
    # =========================================================================

    @staticmethod
    def _create_rag_agent_ir(
        project_id: str,
        project_name: str,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> FlowIRv2:
        """Create IR for RAG agent template.

        Structure:
        - Input -> [Query Rewrite] -> Retriever -> [Reranker] -> Context Builder
        - -> [Citation Guard] -> LLM Answer -> Output

        Engine-specific variations:
        - LangGraph: Uses LangGraph retrieval chains
        - LlamaIndex: Uses LlamaIndex query engines and response synthesizers
        """
        engine_type = TemplateFactory._engine_to_engine_type(engine)
        include_query_rewrite = params.get("include_query_rewrite", True)
        include_reranker = params.get("include_reranker", False)
        include_citations = params.get("include_citations", True)
        top_k = params.get("top_k", 5)
        model = params.get("model", "gpt-4o-mini")

        nodes: list[Node] = []
        edges: list[Edge] = []
        current_node = "input"

        # Node 1: Input (start node)
        nodes.append(
            Node(
                id="input",
                type=NodeType.LLM,
                name="Input Parser",
                params={
                    "model": model,
                    "temperature": 0.3,
                    "system_prompt": "Parse and understand the user's question.",
                    "prompt_template": "{input}",
                    "engine": engine_type.value,
                    "is_start": True,
                },
            )
        )

        # Node 2: Query Rewrite (optional)
        if include_query_rewrite:
            nodes.append(
                Node(
                    id="query_rewrite",
                    type=NodeType.LLM,
                    name="Query Rewriter",
                    params={
                        "model": model,
                        "temperature": 0.3,
                        "system_prompt": (
                            "Rewrite the user's query to be more effective for retrieval. "
                            "Make it specific and include relevant keywords. "
                            "Output only the rewritten query."
                        ),
                        "prompt_template": "Original query: {current}\n\nRewritten query:",
                        "engine": engine_type.value,
                    },
                )
            )
            edges.append(Edge(source=current_node, target="query_rewrite"))
            current_node = "query_rewrite"

        # Node 3: Retriever
        retriever_config = TemplateFactory._get_retriever_config(engine, top_k)
        nodes.append(
            Node(
                id="retriever",
                type=NodeType.RETRIEVER,
                name="Document Retriever",
                params={
                    "query_template": "{current}",
                    "top_k": top_k,
                    "index_name": "default",
                    "index_config": retriever_config,
                    "engine": engine_type.value,
                },
            )
        )
        edges.append(Edge(source=current_node, target="retriever"))
        current_node = "retriever"

        # Node 4: Reranker (optional)
        if include_reranker:
            nodes.append(
                Node(
                    id="reranker",
                    type=NodeType.LLM,
                    name="Reranker",
                    params={
                        "model": model,
                        "temperature": 0.0,
                        "system_prompt": (
                            "You are a relevance judge. Given the query and retrieved documents, "
                            "rerank them by relevance. Output the document IDs in order of relevance."
                        ),
                        "prompt_template": (
                            "Query: {input}\n\nDocuments:\n{citations}\n\nRanked order:"
                        ),
                        "engine": engine_type.value,
                    },
                )
            )
            edges.append(Edge(source=current_node, target="reranker"))
            current_node = "reranker"

        # Node 5: Citation Guard Router (optional)
        if include_citations:
            nodes.append(
                Node(
                    id="citation_guard",
                    type=NodeType.ROUTER,
                    name="Citation Guard",
                    params={
                        "routes": {
                            "sufficient_evidence": "answer_generator",
                            "insufficient_evidence": "abstain_output",
                        },
                        "default_route": "answer_generator",
                        "guard_mode": "retrieval",
                        "guard_config": {
                            "min_docs": 1,
                            "min_top_score": 0.3,
                            "else_branch": "abstain_output",
                        },
                        "engine": engine_type.value,
                    },
                )
            )
            edges.append(Edge(source=current_node, target="citation_guard"))
            current_node = "citation_guard"

            # Add abstain output branch
            nodes.append(
                Node(
                    id="abstain_output",
                    type=NodeType.OUTPUT,
                    name="Abstain Response",
                    params={
                        "output_template": (
                            "I don't have enough relevant information to answer this question "
                            "accurately. Could you please provide more context or rephrase your question?"
                        ),
                        "format": "text",
                    },
                )
            )
            edges.append(
                Edge(
                    source="citation_guard",
                    target="abstain_output",
                    condition="insufficient_evidence",
                )
            )

        # Node 6: Answer Generator (LLM)
        answer_system_prompt = TemplateFactory._get_rag_answer_prompt(engine, include_citations)
        answer_node_params: dict[str, Any] = {
            "model": model,
            "temperature": 0.5,
            "system_prompt": answer_system_prompt,
            "prompt_template": (
                "Question: {input}\n\n"
                "Context from retrieved documents:\n{citations}\n\n"
                "Answer:"
            ),
            "engine": engine_type.value,
        }

        nodes.append(
            Node(
                id="answer_generator",
                type=NodeType.LLM,
                name="Answer Generator",
                params=answer_node_params,
            )
        )

        if include_citations:
            edges.append(
                Edge(
                    source="citation_guard",
                    target="answer_generator",
                    condition="sufficient_evidence",
                )
            )
        else:
            edges.append(Edge(source=current_node, target="answer_generator"))

        # Node 7: Output
        output_template = "{current}"
        if include_citations:
            output_template = "{current}\n\nSources:\n{citations}"

        nodes.append(
            Node(
                id="output",
                type=NodeType.OUTPUT,
                name="Output",
                params={
                    "output_template": output_template,
                    "format": "markdown" if include_citations else "text",
                },
            )
        )
        edges.append(Edge(source="answer_generator", target="output"))

        # Build description
        features = []
        if include_query_rewrite:
            features.append("query rewrite")
        if include_reranker:
            features.append("reranking")
        if include_citations:
            features.append("citations + abstain guard")

        description = f"RAG agent with {', '.join(features) if features else 'basic retrieval'}"

        return TemplateFactory._create_single_agent_ir_v2(
            project_id=project_id,
            project_name=project_name,
            engine_type=engine_type,
            description=description,
            nodes=nodes,
            edges=edges,
            model=model,
            temperature=0.5,
            system_prompt=TemplateFactory._get_rag_answer_prompt(engine, include_citations),
        )

    @staticmethod
    def _get_retriever_config(engine: TargetEngine, top_k: int) -> dict[str, Any]:
        """Get engine-specific retriever configuration."""
        if engine == TargetEngine.LLAMAINDEX:
            return {
                "vector_store": "default",
                "similarity_top_k": top_k,
                "response_mode": "compact",
                "node_postprocessors": ["similarity_cutoff"],
            }
        else:
            return {
                "vector_store": "default",
                "search_type": "similarity",
                "fetch_k": top_k * 2,
                "return_docs": True,
            }

    @staticmethod
    def _get_rag_answer_prompt(engine: TargetEngine, include_citations: bool) -> str:
        """Get engine-specific RAG answer system prompt."""
        base = (
            "You are a helpful assistant that answers questions based on the provided context. "
            "Only use information from the given context to answer."
        )

        if include_citations:
            base += (
                " When citing sources, reference them by their document ID or title. "
                "If the context doesn't contain enough information, acknowledge this limitation."
            )

        if engine == TargetEngine.LLAMAINDEX:
            base += "\n\nUse the LlamaIndex response synthesizer format for structured outputs."
        else:
            base += "\n\nFormat your response clearly with proper markdown when appropriate."

        return base

    # =========================================================================
    # Supervisor + Workers Template (Multi-Agent / IR v2)
    # =========================================================================

    @staticmethod
    def _create_supervisor_workers_ir(
        project_id: str,
        project_name: str,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> FlowIRv2:
        """Create a v2 IR with supervisor + worker agents.

        Structure:
        - Supervisor agent: Router that dispatches to workers
        - Researcher agent: LLM for research tasks
        - Writer agent: LLM for writing tasks
        """
        model = params.get("model", "gpt-4o-mini")
        num_workers = min(max(params.get("num_workers", 2), 2), 4)
        engine_type = TemplateFactory._engine_to_engine_type(engine)

        # Build supervisor agent
        supervisor = AgentSpec(
            id="supervisor",
            name="Supervisor",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="classify",
                        type=NodeType.LLM,
                        name="Classify Task",
                        params={
                            "model": model,
                            "temperature": 0.3,
                            "system_prompt": (
                                "You are a task classifier. Analyze the user request and "
                                "decide which worker should handle it. Reply with one word: "
                                "'researcher' if the task requires gathering information, "
                                "or 'writer' if the task requires creating content."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="route",
                        type=NodeType.ROUTER,
                        name="Route to Worker",
                        params={
                            "routes": {
                                "researcher": "researcher",
                                "writer": "writer",
                            },
                            "default_route": "researcher",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Supervisor Output",
                        params={
                            "output_template": "{current}",
                            "format": "text",
                        },
                    ),
                ],
                edges=[
                    Edge(source="classify", target="route"),
                    Edge(source="route", target="output"),
                ],
                root="classify",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.3,
                system_prompt="You are a supervisor that routes tasks to specialized workers.",
            ),
            budgets=BudgetSpec(max_steps=10, max_depth=3),
        )

        # Build researcher agent
        researcher = AgentSpec(
            id="researcher",
            name="Researcher",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="research",
                        type=NodeType.LLM,
                        name="Research",
                        params={
                            "model": model,
                            "temperature": 0.5,
                            "system_prompt": (
                                "You are a research specialist. Gather information, "
                                "analyze data, and provide comprehensive findings."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Research Output",
                        params={
                            "output_template": "{current}",
                            "format": "text",
                        },
                    ),
                ],
                edges=[Edge(source="research", target="output")],
                root="research",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.5,
                system_prompt="You are a research specialist.",
            ),
            tools_allowlist=["web_search", "url_reader"],
            memory_namespace="researcher_memory",
            budgets=BudgetSpec(max_tokens=50000, max_steps=5),
        )

        # Build writer agent
        writer = AgentSpec(
            id="writer",
            name="Writer",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="write",
                        type=NodeType.LLM,
                        name="Write Content",
                        params={
                            "model": model,
                            "temperature": 0.7,
                            "system_prompt": (
                                "You are a skilled writer. Create clear, engaging content "
                                "based on the given topic or brief."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Writer Output",
                        params={
                            "output_template": "{current}",
                            "format": "markdown",
                        },
                    ),
                ],
                edges=[Edge(source="write", target="output")],
                root="write",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.7,
                system_prompt="You are a skilled content writer.",
            ),
            memory_namespace="writer_memory",
            budgets=BudgetSpec(max_tokens=50000, max_steps=5),
        )

        agents = [supervisor, researcher, writer]

        # Handoff rules
        handoffs = [
            HandoffRule(
                from_agent_id="supervisor",
                to_agent_id="researcher",
                mode=HandoffMode.CALL,
            ),
            HandoffRule(
                from_agent_id="supervisor",
                to_agent_id="writer",
                mode=HandoffMode.CALL,
            ),
        ]

        return FlowIRv2(
            ir_version="2",
            flow=Flow(
                id=project_id,
                name=project_name,
                version="1.0.0",
                engine_preference=engine_type,
                description=f"Multi-agent: supervisor + {num_workers} workers",
            ),
            agents=agents,
            entrypoints=[EntrypointSpec(name="main", agent_id="supervisor")],
            handoffs=handoffs,
            resources=ResourceRegistry(
                shared_memory_namespaces=["researcher_memory", "writer_memory"],
            ),
        )

    @staticmethod
    def _create_oncology_research_team_ir(
        project_id: str,
        project_name: str,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> FlowIRv2:
        """Create a v2 IR for scientific oncology research workflows.

        Agent roles:
        - supervisor: triages requests and routes to specialists
        - genomics_analyst: variant and pathway focused analysis
        - pathology_analyst: histopathology/computational pathology analysis
        - trials_scout: clinical trial matching and eligibility extraction
        """
        model = params.get("model", "gpt-4o-mini")
        include_pathology = params.get("include_pathology", True)
        include_clinical_trials = params.get("include_clinical_trials", True)
        engine_type = TemplateFactory._engine_to_engine_type(engine)

        worker_specs: list[tuple[str, str, str, str, str, str | None, list[str], BudgetSpec]] = [
            (
                "genomics_analyst",
                "Genomics Analyst",
                "analyze_genomics",
                "Analyze Genomics",
                (
                    "You are a genomics specialist for oncology research. Analyze molecular data, "
                    "identify relevant mutations/pathways, and provide concise evidence-aware findings."
                ),
                "genomics_memory",
                ["web_search", "url_reader"],
                BudgetSpec(max_tokens=60000, max_steps=6),
            )
        ]

        if include_pathology:
            worker_specs.append(
                (
                    "pathology_analyst",
                    "Computational Pathology Analyst",
                    "analyze_pathology",
                    "Analyze Pathology",
                    (
                        "You are a computational pathology specialist. Summarize morphology/tissue "
                        "patterns and explain clinically relevant findings with clear caveats."
                    ),
                    "pathology_memory",
                    ["web_search", "url_reader"],
                    BudgetSpec(max_tokens=50000, max_steps=5),
                )
            )

        if include_clinical_trials:
            worker_specs.append(
                (
                    "trials_scout",
                    "Clinical Trials Scout",
                    "find_trials",
                    "Find Clinical Trials",
                    (
                        "You are a clinical trials specialist. Match patient context to trial "
                        "criteria, list likely candidates, and call out uncertainty explicitly."
                    ),
                    "trials_memory",
                    ["web_search", "url_reader"],
                    BudgetSpec(max_tokens=50000, max_steps=5),
                )
            )

        route_targets = {worker_id: worker_id for worker_id, *_ in worker_specs}
        default_route = worker_specs[0][0]

        supervisor = AgentSpec(
            id="supervisor",
            name="Oncology Supervisor",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="triage",
                        type=NodeType.LLM,
                        name="Triage Request",
                        params={
                            "model": model,
                            "temperature": 0.2,
                            "system_prompt": (
                                "You are an oncology research supervisor. Route each request to one "
                                "specialist agent id only: "
                                f"{', '.join(route_targets.keys())}."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="route",
                        type=NodeType.ROUTER,
                        name="Route to Specialist",
                        params={
                            "routes": route_targets,
                            "default_route": default_route,
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Supervisor Output",
                        params={
                            "output_template": "{current}",
                            "format": "text",
                        },
                    ),
                ],
                edges=[
                    Edge(source="triage", target="route"),
                    Edge(source="route", target="output"),
                ],
                root="triage",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.2,
                system_prompt=(
                    "You supervise specialist oncology agents and coordinate safe handoffs."
                ),
            ),
            budgets=BudgetSpec(max_steps=12, max_depth=4),
        )

        workers: list[AgentSpec] = []
        handoffs: list[HandoffRule] = []
        shared_namespaces: list[str] = []

        for (
            worker_id,
            worker_name,
            start_node_id,
            start_node_name,
            worker_prompt,
            memory_namespace,
            tools_allowlist,
            worker_budget,
        ) in worker_specs:
            worker = AgentSpec(
                id=worker_id,
                name=worker_name,
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id=start_node_id,
                            type=NodeType.LLM,
                            name=start_node_name,
                            params={
                                "model": model,
                                "temperature": 0.4,
                                "system_prompt": worker_prompt,
                                "prompt_template": "{input}",
                                "engine": engine_type.value,
                                "is_start": True,
                            },
                        ),
                        Node(
                            id="output",
                            type=NodeType.OUTPUT,
                            name=f"{worker_name} Output",
                            params={
                                "output_template": "{current}",
                                "format": "markdown",
                            },
                        ),
                    ],
                    edges=[Edge(source=start_node_id, target="output")],
                    root=start_node_id,
                ),
                llm=LlmBinding(
                    provider=LLMProvider.AUTO,
                    model=model,
                    temperature=0.4,
                    system_prompt=worker_prompt,
                ),
                tools_allowlist=tools_allowlist,
                memory_namespace=memory_namespace,
                budgets=worker_budget,
            )
            workers.append(worker)
            if memory_namespace:
                shared_namespaces.append(memory_namespace)
            handoffs.append(
                HandoffRule(
                    from_agent_id="supervisor",
                    to_agent_id=worker_id,
                    mode=HandoffMode.CALL,
                )
            )

        description_parts = ["supervisor", "genomics"]
        if include_pathology:
            description_parts.append("pathology")
        if include_clinical_trials:
            description_parts.append("clinical trials")
        description = "Multi-agent oncology research: " + ", ".join(description_parts)

        return FlowIRv2(
            ir_version="2",
            flow=Flow(
                id=project_id,
                name=project_name,
                version="1.0.0",
                engine_preference=engine_type,
                description=description,
            ),
            agents=[supervisor, *workers],
            entrypoints=[EntrypointSpec(name="main", agent_id="supervisor")],
            handoffs=handoffs,
            resources=ResourceRegistry(
                shared_memory_namespaces=shared_namespaces,
            ),
        )

    @staticmethod
    def _create_fullstack_multiagent_ir(
        project_id: str,
        project_name: str,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> FlowIRv2:
        """Create a comprehensive multi-agent IR that uses almost all node types."""
        model = params.get("model", "gpt-4o-mini")
        strict_schema = bool(params.get("strict_schema", False))
        include_mcp_tool = bool(params.get("include_mcp_tool", True))
        engine_type = TemplateFactory._engine_to_engine_type(engine)

        global_policies = PolicySpec(
            tool_allowlist=[
                "search",
                "web_search",
                "url_reader",
                "calculator",
                "datetime",
                "mcp:*",
            ],
            tool_denylist=["python_repl", "shell", "exec"],
            abstain=AbstainSpec(
                enabled=True,
                confidence_threshold=0.35,
                require_citations_for_rag=True,
            ),
            redaction=RedactionSpec(
                enabled=True,
                patterns=[
                    r"(?i)api[_-]?key\\s*=\\s*[^\\s]+",
                    r"(?i)token\\s*=\\s*[^\\s]+",
                ],
                mask="***REDACTED***",
            ),
            input_sanitization=SanitizationSpec(
                enabled=True,
                max_input_chars=12000,
                strip_html=True,
            ),
            allow_schema_soft_fail=not strict_schema,
        )

        supervisor = AgentSpec(
            id="supervisor",
            name="Supervisor",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="triage",
                        type=NodeType.LLM,
                        name="Triage Request",
                        params={
                            "model": model,
                            "temperature": 0.2,
                            "system_prompt": (
                                "Route each request to one specialist: researcher, toolsmith, "
                                "synthesizer, or reliability."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="dispatch",
                        type=NodeType.ROUTER,
                        name="Dispatch Router",
                        params={
                            "routes": {
                                "research": "researcher",
                                "tool": "toolsmith",
                                "synth": "synthesizer",
                                "error": "reliability",
                            },
                            "default_route": "researcher",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Supervisor Output",
                        params={
                            "output_template": "{current}",
                            "format": "text",
                        },
                    ),
                ],
                edges=[
                    Edge(source="triage", target="dispatch"),
                    Edge(source="dispatch", target="output"),
                ],
                root="triage",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.2,
                system_prompt="You supervise specialists and keep responses safe.",
            ),
            budgets=BudgetSpec(max_steps=16, max_depth=4, max_tokens=80000),
            retries=RetrySpec(max_attempts=2, backoff_ms=250, retry_on=["timeout", "rate_limit", "5xx"]),
            fallbacks=FallbackSpec(
                llm_chain=[
                    {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.2},
                    {"provider": "gemini", "model": "gemini-2.5-flash", "temperature": 0.2},
                ],
            ),
        )

        researcher = AgentSpec(
            id="researcher",
            name="Researcher",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="intake",
                        type=NodeType.LLM,
                        name="Research Intake",
                        params={
                            "model": model,
                            "temperature": 0.4,
                            "system_prompt": "Understand the question and create a retrieval query.",
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="fanout",
                        type=NodeType.PARALLEL,
                        name="Parallel Fanout",
                        params={"mode": "broadcast"},
                    ),
                    Node(
                        id="retrieve",
                        type=NodeType.RETRIEVER,
                        name="Retrieve Evidence",
                        params={
                            "query_template": "{current}",
                            "top_k": 6,
                            "index_name": "default",
                            "index_config": {"type": "vector"},
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="memory",
                        type=NodeType.MEMORY,
                        name="Research Memory",
                        params={
                            "memory_type": "summary",
                            "max_tokens": 3000,
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="join_context",
                        type=NodeType.JOIN,
                        name="Join Context",
                        params={"strategy": "dict"},
                    ),
                    Node(
                        id="draft",
                        type=NodeType.LLM,
                        name="Draft Findings",
                        params={
                            "model": model,
                            "temperature": 0.4,
                            "system_prompt": "Draft concise findings grounded in retrieved evidence.",
                            "prompt_template": "{current}",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Research Output",
                        params={"output_template": "{current}", "format": "markdown"},
                    ),
                ],
                edges=[
                    Edge(source="intake", target="fanout"),
                    Edge(source="fanout", target="retrieve"),
                    Edge(source="fanout", target="memory"),
                    Edge(source="retrieve", target="join_context"),
                    Edge(source="memory", target="join_context"),
                    Edge(source="join_context", target="draft"),
                    Edge(source="draft", target="output"),
                ],
                root="intake",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.4,
                system_prompt="You are a research specialist.",
            ),
            tools_allowlist=["web_search", "url_reader"],
            memory_namespace="research_memory",
            budgets=BudgetSpec(max_steps=10, max_depth=3, max_tokens=60000),
            retries=RetrySpec(max_attempts=3, backoff_ms=350, retry_on=["timeout", "rate_limit", "5xx"]),
            policies=PolicySpec(
                tool_allowlist=["web_search", "url_reader"],
                allow_schema_soft_fail=not strict_schema,
            ),
        )

        tool_name = "mcp:pubmed.search" if include_mcp_tool else "search"
        tool_config: dict[str, Any] = {}
        if include_mcp_tool:
            tool_config = {
                "mcp_server": {
                    "tool_name": "pubmed.search",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-pubmed"],
                    "timeout_seconds": 20,
                }
            }

        toolsmith = AgentSpec(
            id="toolsmith",
            name="Toolsmith",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="plan",
                        type=NodeType.LLM,
                        name="Plan Tool Call",
                        params={
                            "model": model,
                            "temperature": 0.1,
                            "system_prompt": "Plan a tool invocation and required arguments.",
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="run_tool",
                        type=NodeType.TOOL,
                        name="Run Tool",
                        params={
                            "tool_name": tool_name,
                            "tool_config": tool_config,
                            "engine": engine_type.value,
                            "retries": {
                                "max_attempts": 3,
                                "backoff_ms": 500,
                                "retry_on": ["timeout", "rate_limit", "5xx", "unknown"],
                                "jitter": True,
                            },
                            "fallbacks": {
                                "tool_fallbacks": {
                                    tool_name: ["search", "web_search"],
                                }
                            },
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Tool Output",
                        params={"output_template": "{current}", "format": "json"},
                    ),
                ],
                edges=[
                    Edge(source="plan", target="run_tool"),
                    Edge(source="run_tool", target="output"),
                ],
                root="plan",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.1,
                system_prompt="You execute tools safely and summarize structured outputs.",
            ),
            tools_allowlist=["search", "web_search", "url_reader", "calculator", "datetime", "mcp:*"],
            memory_namespace="tool_memory",
            budgets=BudgetSpec(max_steps=8, max_depth=3, max_tool_calls=6),
            retries=RetrySpec(max_attempts=3, backoff_ms=400, retry_on=["timeout", "rate_limit", "5xx"]),
        )

        synthesizer = AgentSpec(
            id="synthesizer",
            name="Synthesizer",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="compose",
                        type=NodeType.LLM,
                        name="Compose Final Answer",
                        params={
                            "model": model,
                            "temperature": 0.5,
                            "system_prompt": (
                                "Combine evidence into a final response with citations when available."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Final Output",
                        params={"output_template": "{current}", "format": "markdown"},
                    ),
                ],
                edges=[Edge(source="compose", target="output")],
                root="compose",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.5,
                system_prompt="You synthesize final responses for end users.",
            ),
            budgets=BudgetSpec(max_steps=6, max_depth=2, max_tokens=40000),
            fallbacks=FallbackSpec(
                llm_chain=[
                    {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.5},
                    {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "temperature": 0.5},
                ],
            ),
        )

        reliability = AgentSpec(
            id="reliability",
            name="Reliability",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="route",
                        type=NodeType.ROUTER,
                        name="Reliability Router",
                        params={
                            "routes": {"recover": "runtime_error"},
                            "default_route": "runtime_error",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="runtime_error",
                        type=NodeType.ERROR,
                        name="Runtime Error Handler",
                        params={
                            "error_template": (
                                "A recoverable execution issue occurred. Return a safe fallback answer."
                            )
                        },
                    ),
                    Node(
                        id="recover",
                        type=NodeType.LLM,
                        name="Recovery Response",
                        params={
                            "model": model,
                            "temperature": 0.2,
                            "system_prompt": "Generate a safe fallback response after an execution issue.",
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Reliability Output",
                        params={"output_template": "{current}", "format": "text"},
                    ),
                ],
                edges=[
                    Edge(source="route", target="runtime_error"),
                    Edge(source="runtime_error", target="recover"),
                    Edge(source="recover", target="output"),
                ],
                root="route",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.2,
                system_prompt="You ensure robust fallback behavior.",
            ),
            budgets=BudgetSpec(max_steps=6, max_depth=2),
        )

        schema_input = {"kind": "json_schema", "ref": "schema://handoff_input"}
        schema_output = {"kind": "json_schema", "ref": "schema://handoff_output"}

        return FlowIRv2(
            ir_version="2",
            flow=Flow(
                id=project_id,
                name=project_name,
                version="1.0.0",
                engine_preference=engine_type,
                description=(
                    "Comprehensive Forge multi-agent template using almost all node types "
                    "with policy/retry/fallback/schema features."
                ),
            ),
            agents=[supervisor, researcher, toolsmith, synthesizer, reliability],
            entrypoints=[
                EntrypointSpec(name="main", agent_id="supervisor"),
                EntrypointSpec(name="research", agent_id="researcher"),
                EntrypointSpec(name="tools", agent_id="toolsmith"),
                EntrypointSpec(name="recovery", agent_id="reliability"),
            ],
            handoffs=[
                HandoffRule(
                    from_agent_id="supervisor",
                    to_agent_id="researcher",
                    mode=HandoffMode.CALL,
                    input_schema=schema_input,
                    output_schema=schema_output,
                ),
                HandoffRule(
                    from_agent_id="supervisor",
                    to_agent_id="toolsmith",
                    mode=HandoffMode.CALL,
                    input_schema=schema_input,
                    output_schema=schema_output,
                ),
                HandoffRule(
                    from_agent_id="supervisor",
                    to_agent_id="synthesizer",
                    mode=HandoffMode.CALL,
                    input_schema=schema_input,
                    output_schema=schema_output,
                ),
                HandoffRule(
                    from_agent_id="supervisor",
                    to_agent_id="reliability",
                    mode=HandoffMode.DELEGATE,
                    input_schema=schema_input,
                    output_schema=schema_output,
                ),
            ],
            resources=ResourceRegistry(
                shared_memory_namespaces=["research_memory", "tool_memory"],
                global_tools=["search", "web_search", "url_reader", "calculator", "datetime"],
                schema_contracts={
                    "handoff_input": {
                        "type": "object",
                        "required": ["input"],
                        "properties": {
                            "input": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                    "handoff_output": {
                        "type": "object",
                        "required": ["result"],
                        "properties": {
                            "result": {},
                        },
                        "additionalProperties": True,
                    },
                },
            ),
            policies=global_policies,
        )

    # =========================================================================
    # Pharma Research Copilot Template
    # =========================================================================

    @staticmethod
    def _create_pharma_research_copilot_ir(
        project_id: str,
        project_name: str,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> FlowIRv2:
        """Create a pharma-grade multi-agent research copilot IR.

        Agents: supervisor, researcher (RAG+citations), toolsmith (PubMed/SQL/API/Python/S3),
        validator (QA), synthesizer, reliability.

        NOTE: sql_query, http_request, python_sandbox, s3_get_object are contract tool names.
        They must be implemented and configured externally before the flow can execute those branches.
        """
        model = params.get("model", "gpt-4o-mini")
        strict_schema = bool(params.get("strict_schema", False))
        vector_db_provider = str(params.get("vector_db_provider", "none")).lower()
        engine_type = TemplateFactory._engine_to_engine_type(engine)
        _has_vector = vector_db_provider != "none"
        _vector_tool = f"{vector_db_provider}_vector_ops" if _has_vector else None
        _vector_tools: list[str] = [_vector_tool] if _has_vector else []  # type: ignore[list-item]
        # Pre-compute vector-conditional strings for supervisor and toolsmith
        _sup_vector_label = (
            ", or vector (needs vector DB upsert/query/index operations)"
            if _has_vector else ""
        )
        _sup_vector_token = "|vector" if _has_vector else ""
        _sup_routes: dict[str, str] = {
            "research": "researcher",
            "tool": "toolsmith",
            "validate": "validator",
            "synth": "synthesizer",
            **( {"vector": "vector_indexer"} if _has_vector else {} ),
            "error": "reliability",
        }
        _toolsmith_vector_step = (
            f"(6) Vector DB operations ({_vector_tool}): ensure_collection, upsert, query, delete. "
            if _has_vector else ""
        )

        global_policies = PolicySpec(
            tool_allowlist=[
                "search",
                "web_search",
                "url_reader",
                "calculator",
                "datetime",
                "mcp:*",
                "sql_query",
                "http_request",
                "python_sandbox",
                "s3_get_object",
                *_vector_tools,
            ],
            tool_denylist=["python_repl", "shell", "exec"],
            abstain=AbstainSpec(
                enabled=True,
                confidence_threshold=0.35,
                require_citations_for_rag=True,
            ),
            redaction=RedactionSpec(
                enabled=True,
                patterns=[
                    r"(?i)api[_-]?key\s*=\s*[^\s]+",
                    r"(?i)token\s*=\s*[^\s]+",
                    r"(?i)authorization:\s*bearer\s+[^\s]+",
                ],
                mask="***REDACTED***",
            ),
            input_sanitization=SanitizationSpec(
                enabled=True,
                max_input_chars=12000,
                strip_html=True,
            ),
            allow_schema_soft_fail=not strict_schema,
        )

        supervisor = AgentSpec(
            id="supervisor",
            name="Supervisor",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="triage",
                        type=NodeType.LLM,
                        name="Triage Request",
                        params={
                            "model": model,
                            "temperature": 0.2,
                            "system_prompt": (
                                "You are a supervisor for scientific agentic workflows. "
                                "Classify the request into: research (needs evidence/RAG), "
                                "tool (needs external tools/SQL/API), validate (needs QA checks), "
                                f"synth (needs final narrative){_sup_vector_label}, or error (runtime issues). "
                                f"Output ONLY one token: research|tool|validate|synth{_sup_vector_token}|error."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="dispatch",
                        type=NodeType.ROUTER,
                        name="Dispatch Router",
                        params={
                            "routes": _sup_routes,
                            "default_route": "researcher",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Supervisor Output",
                        params={"output_template": "{current}", "format": "text"},
                    ),
                ],
                edges=[
                    Edge(source="triage", target="dispatch"),
                    Edge(source="dispatch", target="output"),
                ],
                root="triage",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.2,
                system_prompt="You supervise specialists, enforce policies, and prevent unsafe outputs.",
            ),
            budgets=BudgetSpec(max_steps=18, max_depth=4, max_tokens=80000),
            retries=RetrySpec(max_attempts=2, backoff_ms=250, retry_on=["timeout", "rate_limit", "5xx"]),
            fallbacks=FallbackSpec(
                llm_chain=[
                    {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.2},
                    {"provider": "gemini", "model": "gemini-2.5-flash", "temperature": 0.2},
                ],
            ),
        )

        researcher = AgentSpec(
            id="researcher",
            name="Researcher",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="intake",
                        type=NodeType.LLM,
                        name="Research Intake",
                        params={
                            "model": model,
                            "temperature": 0.3,
                            "system_prompt": (
                                "Convert the user question into a retrieval query. "
                                "Prefer precise biomedical terms (genes, biomarkers, drug names, "
                                "trial phase, endpoints). Output only the query string."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="retrieve",
                        type=NodeType.RETRIEVER,
                        name="Retrieve Evidence",
                        params={
                            "query_template": "{current}",
                            "top_k": 8,
                            "index_name": "scientific_corpus",
                            "index_config": {"type": "vector"},
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="memory",
                        type=NodeType.MEMORY,
                        name="Research Memory",
                        params={
                            "memory_type": "summary",
                            "max_tokens": 3000,
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="join_context",
                        type=NodeType.JOIN,
                        name="Join Context",
                        params={"strategy": "dict"},
                    ),
                    Node(
                        id="draft",
                        type=NodeType.LLM,
                        name="Draft Findings (Cited)",
                        params={
                            "model": model,
                            "temperature": 0.2,
                            "system_prompt": (
                                "Draft findings strictly grounded in retrieved evidence. "
                                "Every non-trivial claim must be backed by citations from the "
                                "retrieved context. If evidence is insufficient, abstain and ask "
                                "for missing inputs."
                            ),
                            "prompt_template": "{current}",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Research Output",
                        params={"output_template": "{current}", "format": "markdown"},
                    ),
                ],
                edges=[
                    Edge(source="intake", target="retrieve"),
                    Edge(source="retrieve", target="join_context"),
                    Edge(source="memory", target="join_context"),
                    Edge(source="join_context", target="draft"),
                    Edge(source="draft", target="output"),
                ],
                root="intake",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.3,
                system_prompt="You are a research specialist for biomedical RAG with citation discipline.",
            ),
            tools_allowlist=["web_search", "url_reader", "mcp:*"],
            memory_namespace="research_memory",
            budgets=BudgetSpec(max_steps=12, max_depth=3, max_tokens=60000, max_tool_calls=6),
            retries=RetrySpec(max_attempts=3, backoff_ms=350, retry_on=["timeout", "rate_limit", "5xx"]),
            policies=PolicySpec(
                tool_allowlist=["web_search", "url_reader", "mcp:*"],
                abstain=AbstainSpec(
                    enabled=True,
                    confidence_threshold=0.4,
                    require_citations_for_rag=True,
                ),
                redaction=RedactionSpec(enabled=True, patterns=[], mask="***REDACTED***"),
                input_sanitization=SanitizationSpec(enabled=True, max_input_chars=12000, strip_html=True),
                allow_schema_soft_fail=not strict_schema,
            ),
        )

        # Toolsmith: PubMed (MCP), plus contract tools (sql_query, http_request, python_sandbox, s3_get_object)
        # Contract tools require external implementation — they are included as tool_name references only.
        toolsmith = AgentSpec(
            id="toolsmith",
            name="Toolsmith",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="plan",
                        type=NodeType.LLM,
                        name="Plan Tool Calls",
                        params={
                            "model": model,
                            "temperature": 0.1,
                            "system_prompt": (
                                "Plan safe tool calls for biomedical workflows. "
                                "Prefer: (1) PubMed search, (2) SQL read-only queries, "
                                "(3) internal REST APIs, (4) Python sandbox computations, (5) S3 read. "
                                f"{_toolsmith_vector_step}"
                                "Output a short plan and the first tool call args as JSON."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="pubmed_search",
                        type=NodeType.TOOL,
                        name="PubMed Search (MCP)",
                        params={
                            "tool_name": "mcp:pubmed.search",
                            "tool_config": {
                                "mcp_server": {
                                    "tool_name": "pubmed.search",
                                    "command": "npx",
                                    "args": ["-y", "@modelcontextprotocol/server-pubmed"],
                                    "timeout_seconds": 20,
                                }
                            },
                            "engine": engine_type.value,
                            "retries": {
                                "max_attempts": 3,
                                "backoff_ms": 500,
                                "retry_on": ["timeout", "rate_limit", "5xx", "unknown"],
                                "jitter": True,
                            },
                            "fallbacks": {
                                "tool_fallbacks": {
                                    "mcp:pubmed.search": ["web_search", "search"],
                                }
                            },
                        },
                    ),
                    # Contract tools — tool_name only, require external config/implementation
                    Node(
                        id="sql_query",
                        type=NodeType.TOOL,
                        name="SQL Query (Read Only) [CONTRACT]",
                        params={
                            "tool_name": "sql_query",
                            "tool_config": {
                                "readonly": True,
                                "allowed_schemas": ["clinical", "omics", "pathology"],
                            },
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="http_request",
                        type=NodeType.TOOL,
                        name="Internal REST API Call [CONTRACT]",
                        params={
                            "tool_name": "http_request",
                            "tool_config": {
                                "allowed_hosts": ["internal.api.company", "clinical.api.company"],
                                "timeout_seconds": 15,
                            },
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="python_sandbox",
                        type=NodeType.TOOL,
                        name="Python Sandbox Analysis [CONTRACT]",
                        params={
                            "tool_name": "python_sandbox",
                            "tool_config": {
                                "sandbox": True,
                                "no_network": True,
                                "max_runtime_seconds": 10,
                            },
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="s3_get",
                        type=NodeType.TOOL,
                        name="S3 Get Object (Read Only) [CONTRACT]",
                        params={
                            "tool_name": "s3_get_object",
                            "tool_config": {"readonly": True},
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="summarize",
                        type=NodeType.LLM,
                        name="Summarize Tool Outputs (Structured)",
                        params={
                            "model": model,
                            "temperature": 0.2,
                            "system_prompt": (
                                "Summarize tool outputs into structured findings. "
                                "Preserve provenance: for each finding include source tool + "
                                "identifiers/urls/row counts when available. Do not invent values."
                            ),
                            "prompt_template": "{current}",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Tool Output",
                        params={"output_template": "{current}", "format": "json"},
                    ),
                ],
                edges=[
                    Edge(source="plan", target="pubmed_search"),
                    Edge(source="pubmed_search", target="summarize"),
                    Edge(source="sql_query", target="summarize"),
                    Edge(source="http_request", target="summarize"),
                    Edge(source="python_sandbox", target="summarize"),
                    Edge(source="s3_get", target="summarize"),
                    Edge(source="summarize", target="output"),
                ],
                root="plan",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.1,
                system_prompt="You execute tools safely and return structured outputs with provenance.",
            ),
            tools_allowlist=[
                "search",
                "web_search",
                "url_reader",
                "calculator",
                "datetime",
                "mcp:*",
                "sql_query",
                "http_request",
                "python_sandbox",
                "s3_get_object",
                *_vector_tools,
            ],
            memory_namespace="tool_memory",
            budgets=BudgetSpec(max_steps=10, max_depth=3, max_tokens=60000, max_tool_calls=8),
            retries=RetrySpec(max_attempts=3, backoff_ms=400, retry_on=["timeout", "rate_limit", "5xx"]),
            policies=PolicySpec(
                tool_allowlist=[
                    "search",
                    "web_search",
                    "url_reader",
                    "calculator",
                    "datetime",
                    "mcp:*",
                    "sql_query",
                    "http_request",
                    "python_sandbox",
                    "s3_get_object",
                    *_vector_tools,
                ],
                tool_denylist=["python_repl", "shell", "exec"],
                abstain=AbstainSpec(
                    enabled=True,
                    confidence_threshold=0.35,
                    require_citations_for_rag=False,
                ),
                redaction=RedactionSpec(
                    enabled=True,
                    patterns=[
                        r"(?i)api[_-]?key\s*=\s*[^\s]+",
                        r"(?i)token\s*=\s*[^\s]+",
                        r"(?i)authorization:\s*bearer\s+[^\s]+",
                    ],
                    mask="***REDACTED***",
                ),
                input_sanitization=SanitizationSpec(enabled=True, max_input_chars=12000, strip_html=True),
                allow_schema_soft_fail=not strict_schema,
            ),
        )

        validator = AgentSpec(
            id="validator",
            name="Validator (QA)",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="qa",
                        type=NodeType.LLM,
                        name="Validate Grounding + Safety",
                        params={
                            "model": model,
                            "temperature": 0.0,
                            "system_prompt": (
                                "You are a strict QA agent for biomedical outputs. "
                                "Check: (1) claims supported by citations/tool provenance, "
                                "(2) no PHI/PII leaks, (3) no overconfident medical guidance, "
                                "(4) if insufficient evidence then require abstain. "
                                "Output JSON with fields: pass:boolean, issues:string[], "
                                "action: one of 'retry_research'|'retry_tools'|'ok'|'abstain'."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="QA Output",
                        params={"output_template": "{current}", "format": "json"},
                    ),
                ],
                edges=[Edge(source="qa", target="output")],
                root="qa",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.0,
                system_prompt="You validate grounding, policy compliance, and recommend retry paths.",
            ),
            budgets=BudgetSpec(max_steps=4, max_depth=2, max_tokens=20000),
            policies=PolicySpec(
                tool_allowlist=[],
                abstain=AbstainSpec(
                    enabled=True,
                    confidence_threshold=0.5,
                    require_citations_for_rag=True,
                ),
                redaction=RedactionSpec(enabled=True, patterns=[], mask="***REDACTED***"),
                input_sanitization=SanitizationSpec(enabled=True, max_input_chars=12000, strip_html=True),
                allow_schema_soft_fail=not strict_schema,
            ),
        )

        synthesizer = AgentSpec(
            id="synthesizer",
            name="Synthesizer",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="compose",
                        type=NodeType.LLM,
                        name="Compose Final Answer",
                        params={
                            "model": model,
                            "temperature": 0.4,
                            "system_prompt": (
                                "Compose the final user response. Prefer concise, scientific tone. "
                                "Include citations when available. If QA indicates abstain, clearly "
                                "state what evidence is missing and ask targeted follow-ups."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Final Output",
                        params={"output_template": "{current}", "format": "markdown"},
                    ),
                ],
                edges=[Edge(source="compose", target="output")],
                root="compose",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.4,
                system_prompt="You synthesize final responses for end users.",
            ),
            budgets=BudgetSpec(max_steps=6, max_depth=2, max_tokens=40000),
            fallbacks=FallbackSpec(
                llm_chain=[
                    {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.4},
                    {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "temperature": 0.4},
                ],
            ),
        )

        reliability = AgentSpec(
            id="reliability",
            name="Reliability",
            graph=GraphSpec(
                nodes=[
                    Node(
                        id="route",
                        type=NodeType.ROUTER,
                        name="Reliability Router",
                        params={
                            "routes": {"recover": "runtime_error"},
                            "default_route": "runtime_error",
                            "engine": engine_type.value,
                            "is_start": True,
                        },
                    ),
                    Node(
                        id="runtime_error",
                        type=NodeType.ERROR,
                        name="Runtime Error Handler",
                        params={
                            "error_template": (
                                "A recoverable execution issue occurred. "
                                "Return a safe fallback answer (no guesses)."
                            )
                        },
                    ),
                    Node(
                        id="recover",
                        type=NodeType.LLM,
                        name="Recovery Response",
                        params={
                            "model": model,
                            "temperature": 0.2,
                            "system_prompt": (
                                "Generate a safe fallback response after an execution issue. "
                                "Suggest next steps and what failed (without leaking secrets)."
                            ),
                            "prompt_template": "{input}",
                            "engine": engine_type.value,
                        },
                    ),
                    Node(
                        id="output",
                        type=NodeType.OUTPUT,
                        name="Reliability Output",
                        params={"output_template": "{current}", "format": "text"},
                    ),
                ],
                edges=[
                    Edge(source="route", target="runtime_error"),
                    Edge(source="runtime_error", target="recover"),
                    Edge(source="recover", target="output"),
                ],
                root="route",
            ),
            llm=LlmBinding(
                provider=LLMProvider.AUTO,
                model=model,
                temperature=0.2,
                system_prompt="You ensure robust fallback behavior.",
            ),
            budgets=BudgetSpec(max_steps=6, max_depth=2),
        )

        schema_input = {"kind": "json_schema", "ref": "schema://handoff_input"}
        schema_output = {"kind": "json_schema", "ref": "schema://handoff_output"}

        # Conditionally build vector_indexer agent
        vector_indexer: AgentSpec | None = None
        if _has_vector:
            vector_indexer = AgentSpec(
                id="vector_indexer",
                name="Vector Indexer",
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id="plan_vector",
                            type=NodeType.LLM,
                            name="Plan Vector Operation",
                            params={
                                "model": model,
                                "temperature": 0.1,
                                "system_prompt": (
                                    "Plan vector database operations for biomedical semantic search. "
                                    f"Provider: {vector_db_provider}. "
                                    "Supported operations: ensure_collection (create index), "
                                    "upsert (store vectors), query (nearest-neighbour search), "
                                    "delete (remove vectors by ID). "
                                    "Output a JSON object with: operation, collection, and operation-specific args."
                                ),
                                "prompt_template": "{input}",
                                "engine": engine_type.value,
                                "is_start": True,
                            },
                        ),
                        Node(
                            id="vector_op",
                            type=NodeType.TOOL,
                            name=f"Vector DB Operation ({vector_db_provider})",
                            params={
                                "tool_name": _vector_tool,
                                "tool_config": {
                                    "provider": vector_db_provider,
                                    "default_collection": "scientific_corpus",
                                },
                                "engine": engine_type.value,
                                "retries": {
                                    "max_attempts": 2,
                                    "backoff_ms": 300,
                                    "retry_on": ["timeout", "rate_limit", "5xx"],
                                },
                            },
                        ),
                        Node(
                            id="format_result",
                            type=NodeType.LLM,
                            name="Format Vector Results",
                            params={
                                "model": model,
                                "temperature": 0.1,
                                "system_prompt": (
                                    "Format vector database results for downstream agents. "
                                    "For query results: list matched records with IDs, scores, and payloads. "
                                    "For upsert/delete: confirm operation and count. "
                                    "Preserve all IDs and scores verbatim."
                                ),
                                "prompt_template": "{current}",
                                "engine": engine_type.value,
                            },
                        ),
                        Node(
                            id="output",
                            type=NodeType.OUTPUT,
                            name="Vector Op Output",
                            params={"output_template": "{current}", "format": "json"},
                        ),
                    ],
                    edges=[
                        Edge(source="plan_vector", target="vector_op"),
                        Edge(source="vector_op", target="format_result"),
                        Edge(source="format_result", target="output"),
                    ],
                    root="plan_vector",
                ),
                llm=LlmBinding(
                    provider=LLMProvider.AUTO,
                    model=model,
                    temperature=0.1,
                    system_prompt=(
                        f"You manage {vector_db_provider} vector database operations "
                        "for semantic search and biomedical document indexing."
                    ),
                ),
                tools_allowlist=list(_vector_tools),
                memory_namespace="vector_memory",
                budgets=BudgetSpec(max_steps=6, max_depth=2, max_tokens=20000, max_tool_calls=4),
                retries=RetrySpec(max_attempts=2, backoff_ms=300, retry_on=["timeout", "rate_limit", "5xx"]),
                policies=PolicySpec(
                    tool_allowlist=list(_vector_tools),
                    tool_denylist=["python_repl", "shell", "exec"],
                    abstain=AbstainSpec(
                        enabled=False,
                        confidence_threshold=0.5,
                    ),
                    redaction=RedactionSpec(
                        enabled=True,
                        patterns=[
                            r"(?i)api[_-]?key\s*=\s*[^\s]+",
                            r"(?i)token\s*=\s*[^\s]+",
                        ],
                        mask="***REDACTED***",
                    ),
                    input_sanitization=SanitizationSpec(enabled=True, max_input_chars=12000, strip_html=True),
                    allow_schema_soft_fail=not strict_schema,
                ),
            )

        _flow_description = (
            "Pharma-grade research copilot: RAG with citations + tool execution "
            "(PubMed/SQL/API/Python/S3) + strict validation + synthesis + recovery. "
            "Contract tools (sql_query, http_request, python_sandbox, s3_get_object) "
            "require external implementation/config."
            + (
                f" Vector DB: {vector_db_provider} ({_vector_tool}) via vector_indexer agent."
                if _has_vector else ""
            )
        )
        _agents = [supervisor, researcher, toolsmith, validator, synthesizer, reliability]
        if vector_indexer is not None:
            _agents.append(vector_indexer)

        _entrypoints = [
            EntrypointSpec(name="main", agent_id="supervisor", description="Supervisor routes to specialists."),
            EntrypointSpec(name="research", agent_id="researcher", description="RAG-focused research mode."),
            EntrypointSpec(name="tools", agent_id="toolsmith", description="Tool execution mode."),
            EntrypointSpec(name="validate", agent_id="validator", description="QA validation mode."),
            EntrypointSpec(name="recovery", agent_id="reliability", description="Safe recovery path."),
        ]
        if _has_vector:
            _entrypoints.append(
                EntrypointSpec(name="vector", agent_id="vector_indexer", description="Direct vector DB operations.")
            )

        _handoffs = [
            HandoffRule(
                from_agent_id="supervisor",
                to_agent_id="researcher",
                mode=HandoffMode.CALL,
                input_schema=schema_input,
                output_schema=schema_output,
            ),
            HandoffRule(
                from_agent_id="supervisor",
                to_agent_id="toolsmith",
                mode=HandoffMode.CALL,
                input_schema=schema_input,
                output_schema=schema_output,
            ),
            HandoffRule(
                from_agent_id="supervisor",
                to_agent_id="validator",
                mode=HandoffMode.CALL,
                input_schema=schema_input,
                output_schema=schema_output,
            ),
            HandoffRule(
                from_agent_id="supervisor",
                to_agent_id="synthesizer",
                mode=HandoffMode.CALL,
                input_schema=schema_input,
                output_schema=schema_output,
            ),
            HandoffRule(
                from_agent_id="supervisor",
                to_agent_id="reliability",
                mode=HandoffMode.DELEGATE,
                input_schema=schema_input,
                output_schema=schema_output,
            ),
        ]
        if _has_vector:
            _handoffs.append(
                HandoffRule(
                    from_agent_id="supervisor",
                    to_agent_id="vector_indexer",
                    mode=HandoffMode.CALL,
                    input_schema=schema_input,
                    output_schema=schema_output,
                )
            )

        _shared_namespaces = ["research_memory", "tool_memory"]
        if _has_vector:
            _shared_namespaces.append("vector_memory")

        return FlowIRv2(
            ir_version="2",
            flow=Flow(
                id=project_id,
                name=project_name,
                version="1.0.0",
                engine_preference=engine_type,
                description=_flow_description,
            ),
            agents=_agents,
            entrypoints=_entrypoints,
            handoffs=_handoffs,
            resources=ResourceRegistry(
                shared_memory_namespaces=_shared_namespaces,
                global_tools=["search", "web_search", "url_reader", "calculator", "datetime"],
                schema_contracts={
                    "handoff_input": {
                        "type": "object",
                        "required": ["input"],
                        "properties": {"input": {"type": "string"}},
                        "additionalProperties": True,
                    },
                    "handoff_output": {
                        "type": "object",
                        "required": ["result"],
                        "properties": {"result": {}},
                        "additionalProperties": True,
                    },
                },
            ),
            policies=global_policies,
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @staticmethod
    def compute_template_hash(
        template_id: ProjectTemplateId,
        engine: TargetEngine,
        params: dict[str, Any],
    ) -> str:
        """Compute a deterministic hash for template inputs.

        Useful for caching and comparing template configurations.
        """
        canonical = json.dumps(
            {
                "template_id": template_id.value,
                "engine": engine.value,
                "params": params,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @staticmethod
    def validate_params(
        template_id: ProjectTemplateId,
        params: dict[str, Any],
    ) -> list[str]:
        """Validate template parameters.

        Returns a list of validation error messages (empty if valid).
        """
        errors: list[str] = []
        registry = get_template_registry()
        template_def = registry.get(template_id)

        if template_def is None:
            return [f"Unknown template: {template_id}"]

        for param in template_def.params:
            if param.name in params:
                value = params[param.name]

                # Type validation
                if param.type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Parameter '{param.name}' must be a boolean")
                elif param.type == "string" and not isinstance(value, str):
                    errors.append(f"Parameter '{param.name}' must be a string")
                elif param.type == "integer" and not isinstance(value, int):
                    errors.append(f"Parameter '{param.name}' must be an integer")
                elif param.type == "select":
                    if param.options and value not in param.options:
                        errors.append(
                            f"Parameter '{param.name}' must be one of: {param.options}"
                        )
            elif param.required:
                errors.append(f"Required parameter '{param.name}' is missing")

        return errors
