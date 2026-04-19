import { z } from "zod";

// Engine preference schema
export const enginePreferenceSchema = z.enum(["langchain", "llamaindex", "auto"]);

// Position schema
export const positionSchema = z.object({
  x: z.number(),
  y: z.number(),
});

// Base params with optional engine override
const baseEngineOverride = z.object({
  engine: enginePreferenceSchema.nullable().optional(),
});

// LLM Node params
export const llmNodeParamsSchema = baseEngineOverride.extend({
  provider: z.enum(["auto", "openai", "gemini", "anthropic"]).optional().default("auto"),
  model: z.string().min(1, "Model is required"),
  system_prompt: z.string(),
  temperature: z.number().min(0).max(2),
});

// Tool Node params
export const toolNodeParamsSchema = baseEngineOverride.extend({
  tool_name: z.string().min(1, "Tool name is required"),
  tool_args_schema: z.record(z.unknown()),
});

// Retriever Node params
export const retrieverNodeParamsSchema = baseEngineOverride.extend({
  top_k: z.number().int().min(1).max(100),
  vector_store: z.string().min(1, "Vector store is required"),
  index_name: z.string().min(1, "Index name is required"),
  query_template: z.string(),
});

// Memory Node params
export const memoryNodeParamsSchema = baseEngineOverride.extend({
  mode: z.enum(["short_term", "long_term"]),
  store: z.enum(["sqlite", "redis"]),
});

// Router Node params
export const routerNodeParamsSchema = baseEngineOverride.extend({
  routing_mode: z.enum(["rules", "llm"]),
  rules: z.array(z.object({
    condition: z.string(),
    target_node: z.string(),
  })).optional(),
});

// Output Node params
export const outputNodeParamsSchema = baseEngineOverride.extend({
  format: z.enum(["text", "json"]),
});

export const errorNodeParamsSchema = baseEngineOverride.extend({
  error_template: z.string().optional(),
});

export const parallelNodeParamsSchema = baseEngineOverride.extend({
  mode: z.enum(["broadcast"]).optional(),
});

export const joinNodeParamsSchema = baseEngineOverride.extend({
  strategy: z.enum(["array", "dict", "last_non_null"]).optional(),
});

// Node type schema
export const nodeTypeSchema = z.enum(["llm", "tool", "router", "retriever", "memory", "output", "error", "parallel", "join"]);

// Generic node params (union)
export const nodeParamsSchema = z.union([
  llmNodeParamsSchema,
  toolNodeParamsSchema,
  retrieverNodeParamsSchema,
  memoryNodeParamsSchema,
  routerNodeParamsSchema,
  outputNodeParamsSchema,
  errorNodeParamsSchema,
  parallelNodeParamsSchema,
  joinNodeParamsSchema,
]);

// Flow Node schema
export const flowNodeSchema = z.object({
  id: z.string().min(1, "Node ID is required"),
  type: nodeTypeSchema,
  name: z.string().min(1, "Node name is required"),
  params: z.record(z.unknown()), // Will be validated separately based on type
  position: positionSchema,
});

// Flow Edge schema
export const flowEdgeSchema = z.object({
  id: z.string().min(1, "Edge ID is required"),
  source: z.string().min(1, "Source node ID is required"),
  target: z.string().min(1, "Target node ID is required"),
  label: z.string().optional(),
});

// Flow schema
export const flowSchema = z.object({
  id: z.string(),
  name: z.string().min(1, "Flow name is required"),
  version: z.string(),
  ir_version: z.literal("2"),
  engine_preference: enginePreferenceSchema,
  nodes: z.array(flowNodeSchema),
  edges: z.array(flowEdgeSchema),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

// Run step schema
export const runStepSchema = z.object({
  node_id: z.string(),
  node_type: nodeTypeSchema,
  started_at: z.string(),
  ended_at: z.string().optional(),
  status: z.enum(["pending", "running", "completed", "error"]),
  input: z.unknown().optional(),
  output: z.unknown().optional(),
  tool_call: z.object({
    name: z.string(),
    args: z.record(z.unknown()),
    result: z.unknown().optional(),
  }).optional(),
  retrieval_citations: z.array(z.object({
    source: z.string(),
    content: z.string(),
    score: z.number().optional(),
  })).optional(),
  token_usage: z.object({
    prompt_tokens: z.number(),
    completion_tokens: z.number(),
    total_tokens: z.number(),
  }).optional(),
  cost: z.object({
    amount: z.number(),
    currency: z.string(),
  }).optional(),
  error: z.string().optional(),
});

// Run schema
export const runSchema = z.object({
  id: z.string(),
  flow_id: z.string(),
  status: z.enum(["pending", "running", "completed", "error"]),
  channel: z.string(),
  input: z.string(),
  output: z.string().optional(),
  steps: z.array(runStepSchema),
  created_at: z.string(),
  updated_at: z.string().optional(),
  error: z.string().optional(),
});

// Validation utilities

/**
 * Detect cycles in the flow graph using DFS
 */
export function detectCycles(nodes: { id: string }[], edges: { source: string; target: string }[]): boolean {
  const adjacency = new Map<string, string[]>();

  // Build adjacency list
  for (const node of nodes) {
    adjacency.set(node.id, []);
  }
  for (const edge of edges) {
    const targets = adjacency.get(edge.source);
    if (targets) {
      targets.push(edge.target);
    }
  }

  const visited = new Set<string>();
  const recursionStack = new Set<string>();

  function dfs(nodeId: string): boolean {
    visited.add(nodeId);
    recursionStack.add(nodeId);

    const neighbors = adjacency.get(nodeId) || [];
    for (const neighbor of neighbors) {
      if (!visited.has(neighbor)) {
        if (dfs(neighbor)) return true;
      } else if (recursionStack.has(neighbor)) {
        return true; // Cycle detected
      }
    }

    recursionStack.delete(nodeId);
    return false;
  }

  for (const node of nodes) {
    if (!visited.has(node.id)) {
      if (dfs(node.id)) return true;
    }
  }

  return false;
}

/**
 * Find nodes with no incoming edges (potential start nodes)
 */
export function findStartNodes(nodes: { id: string }[], edges: { source: string; target: string }[]): string[] {
  const nodesWithIncoming = new Set(edges.map(e => e.target));
  return nodes.filter(n => !nodesWithIncoming.has(n.id)).map(n => n.id);
}

/**
 * Validate the entire flow IR
 */
export function validateFlow(flow: unknown): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  // Parse with Zod
  const result = flowSchema.safeParse(flow);
  if (!result.success) {
    errors.push(...result.error.errors.map(e => `${e.path.join(".")}: ${e.message}`));
    return { valid: false, errors };
  }

  const parsedFlow = result.data;

  // Check for cycles
  if (detectCycles(parsedFlow.nodes, parsedFlow.edges)) {
    errors.push("Flow contains cycles, which may not be supported by the backend");
  }

  // Check for start node
  const startNodes = findStartNodes(parsedFlow.nodes, parsedFlow.edges);
  if (parsedFlow.nodes.length > 0 && startNodes.length === 0) {
    errors.push("Flow has no start node (all nodes have incoming edges)");
  }

  // Check that all edge references exist
  const nodeIds = new Set(parsedFlow.nodes.map(n => n.id));
  for (const edge of parsedFlow.edges) {
    if (!nodeIds.has(edge.source)) {
      errors.push(`Edge ${edge.id} references non-existent source node: ${edge.source}`);
    }
    if (!nodeIds.has(edge.target)) {
      errors.push(`Edge ${edge.id} references non-existent target node: ${edge.target}`);
    }
  }

  return { valid: errors.length === 0, errors };
}

// Type exports from schemas
export type FlowSchemaType = z.infer<typeof flowSchema>;
export type FlowNodeSchemaType = z.infer<typeof flowNodeSchema>;
export type FlowEdgeSchemaType = z.infer<typeof flowEdgeSchema>;
