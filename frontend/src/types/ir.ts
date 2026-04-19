// IR (Intermediate Representation) Types for Agent Compiler
// Canonical FE flow types aligned to backend IR v2.

export const IR_VERSION = "2" as const;

export type EnginePreference = "langchain" | "llamaindex" | "auto";

// Node types must be UPPERCASE to match backend
export type NodeType = "LLM" | "Tool" | "Router" | "Retriever" | "Memory" | "Output" | "Error" | "Parallel" | "Join";

export interface NodePosition {
  x: number;
  y: number;
}

// Base params that all nodes share
interface BaseNodeParams {
  engine?: EnginePreference | null;
  is_start?: boolean;
}

// LLM providers
export type LLMProvider = "auto" | "openai" | "gemini" | "anthropic";

// Node-specific parameter types - matching backend exactly
export interface LLMNodeParams extends BaseNodeParams {
  provider: LLMProvider;
  model: string;
  temperature: number;
  system_prompt?: string | null;
  prompt_template: string;
  max_tokens?: number | null;
  retry_count?: number;
  retry_delay?: number;
  timeout_seconds?: number | null;
}

export interface ToolNodeParams extends BaseNodeParams {
  tool_name: string;
  tool_config: Record<string, unknown>;
  retry_count?: number;
  retry_delay?: number;
  timeout_seconds?: number | null;
}

export type RouterMode = "llm" | "guard";

export interface RouterNodeParams extends BaseNodeParams {
  routes: Record<string, string>; // condition -> target node ID
  default_route?: string | null;
  // Guard mode fields
  mode?: RouterMode;
  min_docs?: number;
  min_top_score?: number;
  grounded_branch?: string | null;
  abstain_branch?: string | null;
}

export interface RetrieverNodeParams extends BaseNodeParams {
  query_template: string;
  top_k: number;
  index_name?: string | null;
  index_config: Record<string, unknown>;
}

export interface MemoryNodeParams extends BaseNodeParams {
  memory_type: "buffer" | "summary" | "vector";
  max_tokens: number;
}

export interface OutputNodeParams {
  output_template: string;
  format: "text" | "json" | "markdown";
  is_start?: boolean;
}

export interface ErrorNodeParams extends BaseNodeParams {
  error_template?: string;
}

export interface ParallelNodeParams extends BaseNodeParams {
  mode?: "broadcast";
}

export interface JoinNodeParams extends BaseNodeParams {
  strategy?: "array" | "dict" | "last_non_null";
}

export type NodeParams =
  | LLMNodeParams
  | ToolNodeParams
  | RouterNodeParams
  | RetrieverNodeParams
  | MemoryNodeParams
  | OutputNodeParams
  | ErrorNodeParams
  | ParallelNodeParams
  | JoinNodeParams;

// Node as sent to/from backend (no position - that's frontend only)
export interface FlowNodeBackend {
  id: string;
  type: NodeType;
  name: string;
  params: NodeParams;
}

// Node with frontend-specific position data
export interface FlowNode extends FlowNodeBackend {
  position: NodePosition;
}

// Edge structure - uses "condition" not "label"
export interface FlowEdge {
  source: string;
  target: string;
  condition?: string | null;
}

// Flow metadata
export interface FlowMeta {
  id: string;
  name: string;
  version: string;
  engine_preference: EnginePreference;
  description: string;
}

// Frontend flow with positions
export interface Flow extends FlowMeta {
  ir_version: string;
  // In v2, nodes/edges are a derived canvas view from agents.graph.
  nodes: FlowNode[];
  edges: FlowEdge[];
  created_at?: string;
  updated_at?: string;
  // Multi-agent fields stored in the canonical backend IR.
  agents?: import("./agents").AgentSpec[];
  handoffs?: import("./agents").HandoffRule[];
  entrypoints?: import("./agents").EntrypointSpec[];
  resources?: import("./agents").ResourceRegistry;
  policies?: import("./agents").PolicySpec;
}

// API Response types
export interface FlowListItem {
  id: string;
  name: string;
  version: string;
  description: string;
  engine_preference: string;
  created_at: string;
  updated_at: string;
}

export interface FlowDetailResponse extends FlowListItem {
  ir: import("./agents").FlowIRv2;
}

// Run types
export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped";

// Retrieved document from Retriever step
export interface RetrievedDoc {
  doc_id: string;
  source: string;
  snippet: string;
  score: number;
}

// Citation in output
export interface Citation {
  doc_id: string;
  source: string;
  text: string;
}

// Guard decision info
export interface GuardDecision {
  decision: "grounded" | "abstain";
  threshold: number;
  top_score: number;
  reason?: string;
}

export interface TimelineStep {
  step_id: string;
  node_id: string;
  node_type: string;
  status: StepStatus;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  meta: Record<string, unknown>;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  // Enhanced fields for Guard/Citations
  retrieved_docs?: RetrievedDoc[];
  guard_decision?: GuardDecision;
  citations?: Citation[];
  // Token tracking
  tokens?: { input?: number | null; output?: number | null; total?: number | null } | null;
  model_name?: string | null;
  // Multi-agent fields
  agent_id?: string | null;
  depth?: number;
  parent_step_id?: string | null;
}

export interface Run {
  id: string;
  flow_id: string;
  status: RunStatus;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  timeline: TimelineStep[];
  // Replay related fields
  original_run_id?: string | null;
  replay_mode?: "exact" | "mocked" | null;
  citations?: Citation[];
  // Multi-agent fields
  entrypoint?: string;
  agent_events?: import("./agents").AgentEvent[];
}

export interface RunListItem {
  id: string;
  flow_id: string;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

// Default params for each node type - matching backend defaults
export const DEFAULT_NODE_PARAMS: Record<NodeType, NodeParams> = {
  LLM: {
    provider: "auto",
    model: "gpt-3.5-turbo",
    temperature: 0.7,
    system_prompt: null,
    prompt_template: "{input}",
    max_tokens: null,
    engine: null,
    is_start: false,
    retry_count: 0,
    retry_delay: 1.0,
    timeout_seconds: null,
  },
  Tool: {
    tool_name: "",
    tool_config: {},
    engine: null,
    is_start: false,
    retry_count: 0,
    retry_delay: 1.0,
    timeout_seconds: null,
  },
  Retriever: {
    query_template: "{input}",
    top_k: 5,
    index_name: null,
    index_config: {},
    engine: null,
    is_start: false,
  },
  Memory: {
    memory_type: "buffer",
    max_tokens: 2000,
    engine: null,
    is_start: false,
  },
  Router: {
    routes: {},
    default_route: null,
    engine: null,
    is_start: false,
    mode: "llm",
    min_docs: 1,
    min_top_score: 0.65,
    grounded_branch: null,
    abstain_branch: null,
  },
  Output: {
    output_template: "{result}",
    format: "text",
    is_start: false,
  },
  Error: {
    error_template: "An error occurred while processing this request.",
    is_start: false,
  },
  Parallel: {
    mode: "broadcast",
    is_start: false,
  },
  Join: {
    strategy: "array",
    is_start: false,
  },
};

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  LLM: "LLM",
  Tool: "Tool",
  Router: "Router",
  Retriever: "Retriever",
  Memory: "Memory",
  Output: "Output",
  Error: "Error",
  Parallel: "Parallel",
  Join: "Join",
};

export const NODE_TYPE_COLORS: Record<NodeType, string> = {
  LLM:       "#8b5cf6",   // --node-llm
  Tool:      "#f97316",   // --node-tool
  Router:    "#22c55e",   // --node-router
  Retriever: "#3b82f6",   // --node-retriever
  Memory:    "#ec4899",   // --node-memory
  Output:    "#06b6d4",   // --node-output
  Error:     "#ef4444",   // --accent-error
  Parallel:  "#eab308",   // --node-trigger
  Join:      "#22d3ee",   // --accent-primary
};

// Helper to convert lowercase type to uppercase
export function normalizeNodeType(type: string): NodeType {
  // Handle case variations
  const mapping: Record<string, NodeType> = {
    "llm": "LLM",
    "tool": "Tool",
    "router": "Router",
    "retriever": "Retriever",
    "memory": "Memory",
    "output": "Output",
    "error": "Error",
    "parallel": "Parallel",
    "join": "Join",
  };
  return mapping[type.toLowerCase()] || "LLM";
}
