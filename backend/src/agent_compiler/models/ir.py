"""Intermediate Representation (IR) schema for agent flows.

This module defines the Pydantic models for validating flow definitions,
including nodes, edges, and the overall flow structure.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class NodeType(str, Enum):
    """Supported node types in the flow."""

    LLM = "LLM"
    TOOL = "Tool"
    ROUTER = "Router"
    RETRIEVER = "Retriever"
    MEMORY = "Memory"
    OUTPUT = "Output"
    ERROR = "Error"  # Special node for error handling
    PARALLEL = "Parallel"
    JOIN = "Join"


class EngineType(str, Enum):
    """Supported execution engines."""

    LANGCHAIN = "langchain"
    LLAMAINDEX = "llamaindex"
    AUTO = "auto"


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    AUTO = "auto"  # infer from model name (legacy fallback)


class SchemaKind(str, Enum):
    """Supported schema reference kinds."""

    JSON_SCHEMA = "json_schema"
    PYDANTIC = "pydantic"
    ZOD = "zod"


class SchemaRef(BaseModel):
    """Reference to an external schema artifact."""

    kind: SchemaKind = SchemaKind.JSON_SCHEMA
    ref: str = Field(..., min_length=1)


class RetrySpec(BaseModel):
    """Retry policy specification."""

    max_attempts: int = Field(default=2, ge=1, le=10)
    backoff_ms: int = Field(default=300, ge=0, le=60000)
    retry_on: list[str] = Field(default_factory=lambda: ["timeout", "rate_limit", "5xx"])
    jitter: bool = True


class FallbackSpec(BaseModel):
    """Fallback chain specification."""

    llm_chain: list[dict[str, Any]] = Field(default_factory=list)
    tool_fallbacks: dict[str, list[str]] = Field(default_factory=dict)


class LLMParams(BaseModel):
    """Parameters for LLM nodes."""

    provider: LLMProvider = LLMProvider.AUTO
    model: str = "gpt-3.5-turbo"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    system_prompt: str | None = None
    prompt_template: str = "{input}"
    max_tokens: int | None = None
    engine: EngineType | None = None
    is_start: bool = False
    # Retry & timeout
    retry_count: int = Field(default=0, ge=0, le=10, description="Number of retries on failure")
    retry_delay: float = Field(default=1.0, ge=0.0, description="Seconds between retries")
    timeout_seconds: float | None = Field(default=None, description="Max seconds per attempt")


class ToolParams(BaseModel):
    """Parameters for Tool nodes."""

    tool_name: str
    tool_config: dict[str, Any] = Field(default_factory=dict)
    engine: EngineType | None = None
    is_start: bool = False
    # Retry & timeout
    retry_count: int = Field(default=0, ge=0, le=10, description="Number of retries on failure")
    retry_delay: float = Field(default=1.0, ge=0.0, description="Seconds between retries")
    timeout_seconds: float | None = Field(default=None, description="Max seconds per attempt")
    retries: RetrySpec | None = None
    fallbacks: FallbackSpec | None = None
    input_schema: SchemaRef | None = None
    output_schema: SchemaRef | None = None


class RouterGuardMode(str, Enum):
    """Guard modes for Router nodes."""

    NONE = "none"  # Standard routing (default)
    RETRIEVAL = "retrieval"  # Guard based on retrieval evidence


class RouterGuardConfig(BaseModel):
    """Configuration for Router guard mode."""

    min_docs: int = Field(default=1, ge=0, description="Minimum documents required")
    min_top_score: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Minimum score for top document"
    )
    else_branch: str = Field(
        default="abstain", description="Branch to take when guard fails"
    )


class RouterParams(BaseModel):
    """Parameters for Router nodes."""

    routes: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of condition -> target node ID",
    )
    default_route: str | None = None
    engine: EngineType | None = None
    is_start: bool = False

    # Guard mode for deterministic routing based on retrieval evidence
    guard_mode: RouterGuardMode = Field(
        default=RouterGuardMode.NONE,
        description="Guard mode: 'none' for standard routing, 'retrieval' for evidence-based",
    )
    guard_config: RouterGuardConfig = Field(
        default_factory=RouterGuardConfig,
        description="Configuration for guard mode evaluation",
    )


class RetrieverParams(BaseModel):
    """Parameters for Retriever nodes."""

    query_template: str = "{input}"
    top_k: int = Field(default=5, ge=1, le=100)
    index_name: str | None = None
    index_config: dict[str, Any] = Field(default_factory=dict)
    engine: EngineType | None = None
    is_start: bool = False
    retries: RetrySpec | None = None


class MemoryParams(BaseModel):
    """Parameters for Memory nodes."""

    memory_type: Literal["buffer", "summary", "vector"] = "buffer"
    max_tokens: int = 2000
    engine: EngineType | None = None
    is_start: bool = False


class OutputParams(BaseModel):
    """Parameters for Output nodes."""

    output_template: str = "{result}"
    format: Literal["text", "json", "markdown"] = "text"
    is_start: bool = False


class ErrorParams(BaseModel):
    """Parameters for Error nodes."""

    error_template: str = "An error occurred while processing this request."
    is_start: bool = False


class ParallelParams(BaseModel):
    """Parameters for Parallel fan-out nodes."""

    mode: Literal["broadcast"] = "broadcast"
    is_start: bool = False


class JoinParams(BaseModel):
    """Parameters for Join nodes."""

    strategy: Literal["array", "dict", "last_non_null"] = "array"
    is_start: bool = False


NodeParams = (
    LLMParams
    | ToolParams
    | RouterParams
    | RetrieverParams
    | MemoryParams
    | OutputParams
    | ErrorParams
    | ParallelParams
    | JoinParams
)


class Node(BaseModel):
    """A node in the flow graph."""

    id: str = Field(..., min_length=1)
    type: NodeType
    name: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_params(self) -> "Node":
        """Validate params based on node type."""
        param_classes: dict[NodeType, type[BaseModel]] = {
            NodeType.LLM: LLMParams,
            NodeType.TOOL: ToolParams,
            NodeType.ROUTER: RouterParams,
            NodeType.RETRIEVER: RetrieverParams,
            NodeType.MEMORY: MemoryParams,
            NodeType.OUTPUT: OutputParams,
            NodeType.ERROR: ErrorParams,
            NodeType.PARALLEL: ParallelParams,
            NodeType.JOIN: JoinParams,
        }
        param_class = param_classes.get(self.type)
        if param_class:
            param_class.model_validate(self.params)
        return self

    def get_typed_params(self) -> NodeParams:
        """Get params as typed object."""
        param_classes: dict[NodeType, type[BaseModel]] = {
            NodeType.LLM: LLMParams,
            NodeType.TOOL: ToolParams,
            NodeType.ROUTER: RouterParams,
            NodeType.RETRIEVER: RetrieverParams,
            NodeType.MEMORY: MemoryParams,
            NodeType.OUTPUT: OutputParams,
            NodeType.ERROR: ErrorParams,
            NodeType.PARALLEL: ParallelParams,
            NodeType.JOIN: JoinParams,
        }
        param_class = param_classes[self.type]
        return param_class.model_validate(self.params)


class Edge(BaseModel):
    """An edge connecting two nodes."""

    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    condition: str | None = None

    @field_validator("target")
    @classmethod
    def target_differs_from_source(cls, v: str, info) -> str:
        """Ensure target is different from source."""
        if info.data.get("source") == v:
            raise ValueError("Self-loops are not allowed")
        return v


class Flow(BaseModel):
    """Flow metadata."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = "1.0.0"
    engine_preference: EngineType = EngineType.LANGCHAIN
    description: str = ""


class FlowIR(BaseModel):
    """Complete flow Intermediate Representation."""

    ir_version: Literal["2"] = "2"
    flow: Flow
    nodes: list[Node] = Field(..., min_length=1)
    edges: list[Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_flow_structure(self) -> "FlowIR":
        """Validate the flow structure: DAG, start node, node references."""
        node_ids = {node.id for node in self.nodes}

        # Validate edge references
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"Edge source '{edge.source}' references unknown node")
            if edge.target not in node_ids:
                raise ValueError(f"Edge target '{edge.target}' references unknown node")

        # Find start nodes
        nodes_with_incoming = {edge.target for edge in self.edges}
        marked_start_nodes = [
            node for node in self.nodes if node.params.get("is_start", False)
        ]
        implicit_start_nodes = [
            node for node in self.nodes if node.id not in nodes_with_incoming
        ]

        if marked_start_nodes:
            if len(marked_start_nodes) > 1:
                raise ValueError(
                    f"Multiple nodes marked as start: {[n.id for n in marked_start_nodes]}"
                )
            self._start_node_id = marked_start_nodes[0].id
        elif len(implicit_start_nodes) == 1:
            self._start_node_id = implicit_start_nodes[0].id
        elif len(implicit_start_nodes) > 1:
            raise ValueError(
                f"Ambiguous start nodes (no incoming edges): {[n.id for n in implicit_start_nodes]}. "
                "Mark one with is_start=true"
            )
        else:
            raise ValueError("No start node found")

        # Validate DAG (no cycles)
        self._validate_dag(node_ids)

        return self

    def _validate_dag(self, node_ids: set[str]) -> None:
        """Validate that the graph is a DAG (no cycles)."""
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in self.edges:
            adjacency[edge.source].append(edge.target)

        # Kahn's algorithm for topological sort / cycle detection
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        for edge in self.edges:
            in_degree[edge.target] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0

        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(node_ids):
            raise ValueError("Flow contains a cycle - only DAGs are supported in MVP")

    @property
    def start_node_id(self) -> str:
        """Get the ID of the start node."""
        return getattr(self, "_start_node_id", self.nodes[0].id)

    def get_node(self, node_id: str) -> Node | None:
        """Get a node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_topological_order(self) -> list[str]:
        """Get nodes in topological order."""
        node_ids = {node.id for node in self.nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in self.edges:
            adjacency[edge.source].append(edge.target)

        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        for edge in self.edges:
            in_degree[edge.target] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result: list[str] = []

        while queue:
            # Sort for deterministic ordering
            queue.sort()
            node = queue.pop(0)
            result.append(node)
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    def get_successors(self, node_id: str) -> list[str]:
        """Get successor node IDs for a given node."""
        return [edge.target for edge in self.edges if edge.source == node_id]

    def get_predecessors(self, node_id: str) -> list[str]:
        """Get predecessor node IDs for a given node."""
        return [edge.source for edge in self.edges if edge.target == node_id]


# =============================================================================
# IR Parsing
# =============================================================================


def parse_ir(data: dict) -> "FlowIRv2":
    """Parse raw IR data as v2 only.

    Raises:
        ValueError: If the payload is not IR v2.
    """
    from agent_compiler.models.ir_v2 import FlowIRv2
    from agent_compiler.models.ir_v2_to_v2_1 import migrate_v2_to_v2_1_defaults

    version = data.get("ir_version")
    if version != "2":
        raise ValueError("Only ir_version='2' is supported.")
    return migrate_v2_to_v2_1_defaults(FlowIRv2.model_validate(data))
