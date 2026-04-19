// Multi-agent types for IR v2
// Matches backend ir_v2.py schema

export type HandoffMode = "call" | "delegate";

export interface BudgetSpec {
  max_tokens?: number | null;
  max_tool_calls?: number | null;
  max_steps?: number | null;
  max_depth: number;
}

export type SchemaKind = "json_schema" | "pydantic" | "zod";

export interface SchemaRef {
  kind: SchemaKind;
  ref: string;
}

export interface AbstainSpec {
  enabled: boolean;
  reason_template: string;
  confidence_threshold: number;
  require_citations_for_rag: boolean;
}

export interface RedactionSpec {
  enabled: boolean;
  patterns: string[];
  mask: string;
}

export interface SanitizationSpec {
  enabled: boolean;
  max_input_chars: number;
  strip_html: boolean;
}

export interface PolicySpec {
  tool_allowlist: string[];
  tool_denylist: string[];
  max_tool_calls?: number | null;
  max_steps?: number | null;
  max_depth?: number | null;
  abstain: AbstainSpec;
  redaction: RedactionSpec;
  input_sanitization: SanitizationSpec;
  allow_schema_soft_fail: boolean;
}

export interface RetrySpec {
  max_attempts: number;
  backoff_ms: number;
  retry_on: string[];
  jitter: boolean;
}

export interface FallbackSpec {
  llm_chain: Array<Record<string, unknown>>;
  tool_fallbacks: Record<string, string[]>;
}

export interface LlmBinding {
  provider: string;
  model: string;
  temperature: number;
  system_prompt?: string | null;
}

export interface GraphSpec {
  nodes: import("./ir").FlowNodeBackend[];
  edges: import("./ir").FlowEdge[];
  root: string;
}

export interface AgentSpec {
  id: string;
  name: string;
  graph: GraphSpec;
  llm: LlmBinding;
  tools_allowlist: string[];
  memory_namespace?: string | null;
  budgets: BudgetSpec;
  policies?: PolicySpec | null;
  retries?: RetrySpec | null;
  fallbacks?: FallbackSpec | null;
}

export interface HandoffGuard {
  condition_template: string;
  fallback_agent_id?: string | null;
}

export interface HandoffRule {
  from_agent_id: string;
  to_agent_id: string;
  mode: HandoffMode;
  guard?: HandoffGuard | null;
  input_schema?: SchemaRef | null;
  output_schema?: SchemaRef | null;
}

export interface EntrypointSpec {
  name: string;
  agent_id: string;
  description: string;
}

export interface ResourceRegistry {
  shared_memory_namespaces: string[];
  global_tools: string[];
  schema_contracts: Record<string, Record<string, unknown>>;
}

export interface FlowIRv2 {
  ir_version: "2";
  flow: import("./ir").FlowMeta;
  agents: AgentSpec[];
  entrypoints: EntrypointSpec[];
  handoffs: HandoffRule[];
  resources: ResourceRegistry;
  policies?: PolicySpec;
}

// Agent timeline event types
export type AgentEventType =
  | "agent_start"
  | "agent_end"
  | "handoff"
  | "budget_warning"
  | "budget_exceeded"
  | "retry_attempt"
  | "fallback_used"
  | "schema_validation_error"
  | "guard_block";

export interface AgentEvent {
  id: string;
  event_type: AgentEventType;
  agent_id: string;
  parent_agent_id?: string | null;
  depth: number;
  data: Record<string, unknown>;
  timestamp: string | null;
}

// Helper to check if IR is v2
export function isV2IR(ir: unknown): ir is FlowIRv2 {
  return (
    typeof ir === "object" &&
    ir !== null &&
    "ir_version" in ir &&
    (ir as { ir_version: string }).ir_version === "2" &&
    "agents" in ir
  );
}
