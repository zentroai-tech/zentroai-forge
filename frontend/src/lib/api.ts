import type {
  Flow,
  FlowListItem,
  FlowDetailResponse,
  FlowNode,
  FlowEdge,
  FlowNodeBackend,
  Run,
  RunListItem,
  NodeType,
  IR_VERSION
} from "@/types/ir";
import type {
  EvalSuite,
  EvalSuiteListItem,
  EvalCase,
  EvalRun,
  CreateEvalSuitePayload,
  CreateEvalCasePayload,
} from "@/types/eval";
import type {
  GitOpsConfig,
  GitOpsJobStatus,
  GitOpsBackendStatus,
  GitOpsExportResponse,
  GitHubRepo,
  GitHubBranch,
} from "@/types/gitops";
import type {
  TemplateDTO,
  CreateProjectRequest,
  CreateProjectResponse,
  Engine,
} from "@/types/template";
import { FALLBACK_TEMPLATES } from "@/types/template";
import type { ToolContractSummary } from "@/types/tools";
import type {
  Credential,
  CredentialListResponse,
  CreateCredentialRequest,
  UpdateCredentialRequest,
  TestCredentialResponse,
  CredentialScopeType,
} from "@/types/credentials";
import type {
  FlowIRv2,
  AgentSpec,
  ResourceRegistry,
  HandoffRule,
  LlmBinding,
  BudgetSpec,
  PolicySpec,
  RetrySpec,
  FallbackSpec,
  SchemaRef,
} from "@/types/agents";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const DEFAULT_V2_RESOURCES: ResourceRegistry = {
  shared_memory_namespaces: [],
  global_tools: [],
  schema_contracts: {},
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `API Error: ${response.status} ${response.statusText}`;
    try {
      const errorBody = await response.json();
      if (errorBody.detail) {
        message = typeof errorBody.detail === "string"
          ? errorBody.detail
          : JSON.stringify(errorBody.detail);
      } else if (errorBody.message) {
        message = errorBody.message;
      }
    } catch {
      // Could not parse error body
    }
    throw new ApiError(response.status, response.statusText, message);
  }

  // Handle empty responses (204 No Content, etc.)
  const contentLength = response.headers.get("content-length");
  if (response.status === 204 || contentLength === "0") {
    return undefined as T;
  }

  // Try to parse JSON, return undefined if empty
  const text = await response.text();
  if (!text || text.trim() === "") {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const defaultHeaders: HeadersInit = {
    "Content-Type": "application/json",
  };

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  return handleResponse<T>(response);
}

// Storage for node positions (not stored in backend)
const positionStorage = new Map<string, Map<string, { x: number; y: number }>>();
const FLOW_NODE_POSITIONS_KEY = "flow-node-positions-v2";

function savePositions(flowId: string, nodes: FlowNode[]) {
  const positions = new Map<string, { x: number; y: number }>();
  nodes.forEach(node => {
    positions.set(node.id, node.position);
  });
  positionStorage.set(flowId, positions);

  // Also persist to localStorage
  try {
    const allPositions: Record<string, Record<string, { x: number; y: number }>> = {};
    positionStorage.forEach((nodePositions, fId) => {
      allPositions[fId] = Object.fromEntries(nodePositions);
    });
    localStorage.setItem(FLOW_NODE_POSITIONS_KEY, JSON.stringify(allPositions));
  } catch {
    // Ignore localStorage errors
  }
}

function loadPositions(flowId: string): Map<string, { x: number; y: number }> {
  // Try memory first
  if (positionStorage.has(flowId)) {
    return positionStorage.get(flowId)!;
  }

  // Try localStorage
  try {
    const stored = localStorage.getItem(FLOW_NODE_POSITIONS_KEY);
    if (stored) {
      const allPositions = JSON.parse(stored);
      if (allPositions[flowId]) {
        const positions = new Map(Object.entries(allPositions[flowId])) as Map<string, { x: number; y: number }>;
        positionStorage.set(flowId, positions);
        return positions;
      }
    }
  } catch {
    // Ignore localStorage errors
  }

  return new Map();
}

// Convert backend flow response to frontend Flow
function backendToFrontendFlow(response: FlowDetailResponse): Flow {
  const positions = loadPositions(response.id);
  const irData = response.ir as unknown as FlowIRv2;
  if ((irData as { ir_version?: string })?.ir_version !== "2") {
    throw new Error("Only IR v2 is supported by this frontend.");
  }

  const v2 = irData as FlowIRv2;
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  const nodeIdMap = new Map<string, string>();

  v2.agents.forEach((agent, agentIndex) => {
    agent.graph.nodes.forEach((node, nodeIndex) => {
      const visualId = `${agent.id}::${node.id}`;
      nodeIdMap.set(`${agent.id}:${node.id}`, visualId);
      nodes.push({
        ...node,
        id: visualId,
        params: node.params,
        position: positions.get(visualId) || {
          x: 120 + agentIndex * 340 + (nodeIndex % 2) * 170,
          y: 110 + Math.floor(nodeIndex / 2) * 150,
        },
      });
    });
  });

  v2.agents.forEach((agent) => {
    agent.graph.edges.forEach((edge) => {
      const source = nodeIdMap.get(`${agent.id}:${edge.source}`);
      const target = nodeIdMap.get(`${agent.id}:${edge.target}`);
      if (source && target) {
        edges.push({
          source,
          target,
          condition: edge.condition ?? null,
        });
      }
    });
  });

  return {
    id: response.id,
    name: response.name,
    version: response.version,
    description: response.description || "",
    engine_preference: response.engine_preference as Flow["engine_preference"],
    ir_version: "2",
    nodes,
    edges,
    agents: v2.agents,
    handoffs: v2.handoffs,
    entrypoints: v2.entrypoints,
    resources: {
      ...DEFAULT_V2_RESOURCES,
      ...(v2.resources || {}),
      schema_contracts: v2.resources?.schema_contracts || {},
    },
    policies: v2.policies,
    created_at: response.created_at,
    updated_at: response.updated_at,
  };
}

// Convert frontend Flow to the backend IR payload format
export function frontendToBackendIR(flow: Flow): FlowIRv2 {
  if (flow.ir_version !== "2" || !Array.isArray(flow.agents) || flow.agents.length === 0) {
    throw new Error("Only IR v2 is supported by this frontend.");
  }

  savePositions(flow.id, flow.nodes || []);
  const agentNodes = new Map<string, FlowNodeBackend[]>();
  const agentEdges = new Map<string, FlowEdge[]>();

  for (const node of flow.nodes || []) {
    const separatorIndex = node.id.indexOf("::");
    if (separatorIndex <= 0) {
      continue;
    }
    const agentId = node.id.slice(0, separatorIndex);
    const originalId = node.id.slice(separatorIndex + 2);
    const { position, ...backendNode } = node;
    const normalizedNode: FlowNodeBackend = {
      ...backendNode,
      id: originalId,
    };

    if (!agentNodes.has(agentId)) {
      agentNodes.set(agentId, []);
    }
    agentNodes.get(agentId)!.push(normalizedNode);
  }

  for (const edge of flow.edges || []) {
    const sourceSep = edge.source.indexOf("::");
    const targetSep = edge.target.indexOf("::");
    if (sourceSep <= 0 || targetSep <= 0) {
      continue;
    }

    const sourceAgent = edge.source.slice(0, sourceSep);
    const targetAgent = edge.target.slice(0, targetSep);
    if (sourceAgent !== targetAgent) {
      continue;
    }

    const source = edge.source.slice(sourceSep + 2);
    const target = edge.target.slice(targetSep + 2);
    if (!agentEdges.has(sourceAgent)) {
      agentEdges.set(sourceAgent, []);
    }
    agentEdges.get(sourceAgent)!.push({
      source,
      target,
      condition: edge.condition ?? null,
    });
  }

  const v2Agents: AgentSpec[] = (flow.agents || []).map((agent) => {
    const nodesForAgent = agentNodes.get(agent.id) || agent.graph.nodes;
    const edgesForAgent = agentEdges.get(agent.id) || agent.graph.edges;
    const startNode = nodesForAgent.find((n) =>
      Boolean((n.params as unknown as Record<string, unknown>)?.is_start)
    );
    const fallbackRoot = agent.graph.root || nodesForAgent[0]?.id || "root";

    return {
      ...agent,
      graph: {
        ...agent.graph,
        nodes: nodesForAgent,
        edges: edgesForAgent,
        root: startNode?.id || fallbackRoot,
      },
    };
  });

  const normalizedHandoffs = (flow.handoffs || []).map((handoff) => {
    const normalizeSchema = (schema: typeof handoff.input_schema) => {
      if (!schema) return null;
      if (!schema.ref || !String(schema.ref).trim()) return null;
      return schema;
    };
    return {
      ...handoff,
      input_schema: normalizeSchema(handoff.input_schema),
      output_schema: normalizeSchema(handoff.output_schema),
    };
  });

  return {
    ir_version: "2",
    flow: {
      id: flow.id,
      name: flow.name,
      version: flow.version,
      engine_preference: flow.engine_preference,
      description: flow.description || "",
    },
    agents: v2Agents,
    entrypoints: flow.entrypoints || [{ name: "main", agent_id: v2Agents[0]?.id || "main", description: "" }],
    handoffs: normalizedHandoffs,
    resources: {
      ...DEFAULT_V2_RESOURCES,
      ...(flow.resources || {}),
      schema_contracts: flow.resources?.schema_contracts || {},
    },
    policies: flow.policies,
  };
}

// Flow API endpoints

export async function listFlows(): Promise<FlowListItem[]> {
  return fetchApi<FlowListItem[]>("/flows");
}

export async function getFlow(flowId: string): Promise<Flow> {
  const response = await fetchApi<FlowDetailResponse>(`/flows/${flowId}`);
  return backendToFrontendFlow(response);
}

// Response type for create/update (doesn't include ir)
interface FlowSaveResponse {
  id: string;
  name: string;
  version: string;
  description: string;
  engine_preference: string;
  created_at: string;
  updated_at: string;
}

export async function createFlow(flow: Flow): Promise<Flow> {
  const ir = frontendToBackendIR(flow);
  const response = await fetchApi<FlowSaveResponse>("/flows", {
    method: "POST",
    body: JSON.stringify(ir),
  });

  // Create/update don't return ir, so merge with existing flow data
  return {
    ...flow,
    id: response.id,
    name: response.name,
    version: response.version,
    description: response.description,
    engine_preference: response.engine_preference as Flow["engine_preference"],
    created_at: response.created_at,
    updated_at: response.updated_at,
  };
}

export async function updateFlow(flowId: string, flow: Flow): Promise<Flow> {
  const ir = frontendToBackendIR(flow);
  const response = await fetchApi<FlowSaveResponse>(`/flows/${flowId}`, {
    method: "PUT",
    body: JSON.stringify(ir),
  });

  // Create/update don't return ir, so merge with existing flow data
  return {
    ...flow,
    id: response.id,
    name: response.name,
    version: response.version,
    description: response.description,
    engine_preference: response.engine_preference as Flow["engine_preference"],
    created_at: response.created_at,
    updated_at: response.updated_at,
  };
}

export async function deleteFlow(flowId: string): Promise<void> {
  await fetchApi<void>(`/flows/${flowId}`, {
    method: "DELETE",
  });
}

// Flow Version History
export interface FlowVersionItem {
  id: string;
  version_number: number;
  label: string;
  created_at: string;
}

export async function listFlowVersions(flowId: string, limit = 50): Promise<FlowVersionItem[]> {
  return fetchApi<FlowVersionItem[]>(`/flows/${flowId}/versions?limit=${limit}`);
}

export async function restoreFlowVersion(flowId: string, versionNumber: number): Promise<FlowSaveResponse> {
  return fetchApi<FlowSaveResponse>(`/flows/${flowId}/versions/restore`, {
    method: "POST",
    body: JSON.stringify({ version_number: versionNumber }),
  });
}

export async function labelFlowVersion(flowId: string, versionNumber: number, label: string): Promise<FlowVersionItem> {
  return fetchApi<FlowVersionItem>(`/flows/${flowId}/versions/${versionNumber}`, {
    method: "PATCH",
    body: JSON.stringify({ label }),
  });
}

// Run API endpoints

export async function listRuns(flowId: string): Promise<RunListItem[]> {
  return fetchApi<RunListItem[]>(`/flows/${flowId}/runs`);
}

export async function createRun(
  flowId: string,
  input: Record<string, unknown> = {},
  entrypoint?: string
): Promise<Run> {
  const payload: { input: Record<string, unknown>; entrypoint?: string } = { input };
  if (entrypoint) {
    payload.entrypoint = entrypoint;
  }
  return fetchApi<Run>(`/flows/${flowId}/runs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteRun(runId: string): Promise<void> {
  await fetchApi<void>(`/runs/${runId}`, { method: "DELETE" });
}

export async function deleteAllRuns(flowId: string): Promise<{ deleted: number }> {
  return fetchApi<{ deleted: number }>(`/flows/${flowId}/runs`, { method: "DELETE" });
}

export async function getRun(runId: string): Promise<Run> {
  return fetchApi<Run>(`/runs/${runId}`);
}

// Export flow as ZIP
export async function exportFlow(flowId: string, flowName: string): Promise<void> {
  const url = `${API_BASE_URL}/flows/${flowId}/export`;

  const response = await fetch(url, {
    method: "POST",
  });

  if (!response.ok) {
    let message = `Export failed: ${response.status} ${response.statusText}`;
    try {
      const errorBody = await response.json();
      if (errorBody.detail) {
        message = typeof errorBody.detail === "string"
          ? errorBody.detail
          : JSON.stringify(errorBody.detail);
      }
    } catch {
      // Could not parse error body
    }
    throw new Error(message);
  }

  // Download the ZIP file
  const blob = await response.blob();
  const cd = response.headers.get("content-disposition");
  const utf8 = cd?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = cd?.match(/filename=\"?([^\";]+)\"?/i)?.[1];
  const serverFilename = utf8 ? decodeURIComponent(utf8) : plain;
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = serverFilename || `${flowName.replace(/[^a-zA-Z0-9-_]/g, "_")}_export.zip`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(downloadUrl);
  document.body.removeChild(a);
}

// Health check
export async function healthCheck(): Promise<{ status: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (response.ok) {
      return { status: "ok" };
    }
    return { status: "error" };
  } catch {
    return { status: "unreachable" };
  }
}

// ============================================
// Replay API endpoints
// ============================================

export type ReplayMode = "exact" | "mock_tools" | "mock_all";

export async function replayRun(
  runId: string,
  mode: ReplayMode = "exact"
): Promise<Run> {
  return fetchApi<Run>(`/runs/${runId}/replay`, {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
}

export async function getRunComparison(
  runId: string,
  originalRunId: string
): Promise<{
  output_diff: { added: string[]; removed: string[] };
  decision_diff: { field: string; original: unknown; replay: unknown }[];
  score_diff: { original: number; replay: number };
}> {
  return fetchApi(`/runs/${runId}/compare/${originalRunId}`);
}

export interface RunEvent {
  id: string;
  run_id: string;
  ts: string | null;
  seq: number;
  node_id: string;
  type: "LLM_PROMPT" | "LLM_RESPONSE" | "TOOL_CALL" | "TOOL_RESULT" | "RETRIEVAL" | "ROUTER_DECISION" | "POLICY_BLOCK";
  payload: Record<string, unknown>;
  hash: string | null;
}

export async function getRunEvents(runId: string): Promise<RunEvent[]> {
  return fetchApi<RunEvent[]>(`/runs/${runId}/events`);
}

export interface RunNodeDiff {
  node_id: string;
  node_type: string;
  status_a: string;
  status_b: string;
  output_changed: boolean;
  output_diff: { removed: string[]; added: string[] };
  tokens_a: number;
  tokens_b: number;
  token_delta: number;
  duration_ms_a: number;
  duration_ms_b: number;
  duration_delta_ms: number;
  model_a: string | null;
  model_b: string | null;
}

export interface RunDiffResult {
  run_a: { id: string; status: string; duration_ms: number | null; created_at: string; total_tokens: number };
  run_b: { id: string; status: string; duration_ms: number | null; created_at: string; total_tokens: number };
  summary: {
    total_nodes: number;
    changed_nodes: number;
    unchanged_nodes: number;
    token_delta: number;
    duration_delta_ms: number;
    tool_failure_rate_a: number;
    tool_failure_rate_b: number;
  };
  node_diffs: RunNodeDiff[];
}

export async function diffRuns(runAId: string, runBId: string): Promise<RunDiffResult> {
  return fetchApi<RunDiffResult>("/runs/diff", {
    method: "POST",
    body: JSON.stringify({ run_a: runAId, run_b: runBId }),
  });
}

// ============================================
// Eval Suites API endpoints
// (Prefer importing from @/lib/evalsApi for new code)
// ============================================

export async function listEvalSuites(flowId: string): Promise<EvalSuiteListItem[]> {
  return fetchApi<EvalSuiteListItem[]>(`/evals/flows/${flowId}/suites?limit=50&offset=0`);
}

export async function getEvalSuite(suiteId: string): Promise<EvalSuite> {
  return fetchApi<EvalSuite>(`/evals/suites/${suiteId}`);
}

export async function createEvalSuite(
  flowId: string,
  payload: CreateEvalSuitePayload
): Promise<EvalSuite> {
  return fetchApi<EvalSuite>(`/evals/flows/${flowId}/suites`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteEvalSuite(suiteId: string): Promise<void> {
  await fetchApi<void>(`/evals/suites/${suiteId}`, {
    method: "DELETE",
  });
}

export async function createEvalCase(
  suiteId: string,
  payload: CreateEvalCasePayload
): Promise<EvalCase> {
  return fetchApi<EvalCase>(`/evals/suites/${suiteId}/cases`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runEvalSuite(suiteId: string): Promise<EvalRun> {
  return fetchApi<EvalRun>(`/evals/suites/${suiteId}/run`, {
    method: "POST",
  });
}

// ============================================
// GitOps API endpoints
// ============================================

export async function getGitOpsStatus(): Promise<GitOpsBackendStatus> {
  return fetchApi<GitOpsBackendStatus>("/gitops/status");
}

export async function createGitOpsExport(
  exportId: string,
  config: GitOpsConfig
): Promise<GitOpsExportResponse> {
  return fetchApi<GitOpsExportResponse>(`/exports/${exportId}/gitops`, {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function getGitOpsJobStatus(jobId: string): Promise<GitOpsJobStatus> {
  return fetchApi<GitOpsJobStatus>(`/gitops/jobs/${jobId}`);
}

export async function connectGitHub(token: string): Promise<{ status: string; username: string }> {
  return fetchApi<{ status: string; username: string }>("/gitops/connect", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function disconnectGitHub(): Promise<void> {
  await fetchApi<void>("/gitops/disconnect", { method: "DELETE" });
}

export async function listGitHubRepos(query?: string, page?: number): Promise<GitHubRepo[]> {
  const params = new URLSearchParams();
  if (query) params.append("query", query);
  if (page) params.append("page", String(page));
  const qs = params.toString();
  return fetchApi<GitHubRepo[]>(`/gitops/repos${qs ? `?${qs}` : ""}`);
}

export async function listGitHubBranches(owner: string, repo: string): Promise<GitHubBranch[]> {
  return fetchApi<GitHubBranch[]>(`/gitops/repos/${owner}/${repo}/branches`);
}

// ============================================
// Template API endpoints
// ============================================

export async function listTemplates(): Promise<TemplateDTO[]> {
  try {
    return await fetchApi<TemplateDTO[]>("/project-templates");
  } catch {
    // Fallback to hardcoded templates if API unavailable
    return FALLBACK_TEMPLATES;
  }
}

export async function listToolContracts(): Promise<ToolContractSummary[]> {
  return fetchApi<ToolContractSummary[]>("/tool-contracts");
}

export async function createProjectFromTemplate(
  request: CreateProjectRequest
): Promise<CreateProjectResponse> {
  return fetchApi<CreateProjectResponse>("/projects", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// ============================================
// Credentials API endpoints
// ============================================

export async function listCredentials(
  scopeType?: CredentialScopeType,
  scopeId?: string,
  provider?: string
): Promise<Credential[]> {
  const params = new URLSearchParams();
  if (scopeType) params.append("scope_type", scopeType);
  if (scopeId) params.append("scope_id", scopeId);
  if (provider) params.append("provider", provider);
  const query = params.toString();
  const response = await fetchApi<CredentialListResponse>(`/api/credentials${query ? `?${query}` : ""}`);
  return response.credentials;
}

export async function getCredential(credentialId: string): Promise<Credential> {
  return fetchApi<Credential>(`/api/credentials/${credentialId}`);
}

export async function createCredential(
  request: CreateCredentialRequest
): Promise<Credential> {
  return fetchApi<Credential>("/api/credentials", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function updateCredential(
  credentialId: string,
  request: UpdateCredentialRequest
): Promise<Credential> {
  return fetchApi<Credential>(`/api/credentials/${credentialId}`, {
    method: "PATCH",
    body: JSON.stringify(request),
  });
}

export async function deleteCredential(credentialId: string): Promise<void> {
  await fetchApi<void>(`/api/credentials/${credentialId}`, {
    method: "DELETE",
  });
}

export async function testCredential(
  credentialId: string
): Promise<TestCredentialResponse> {
  return fetchApi<TestCredentialResponse>(`/api/credentials/${credentialId}/test`, {
    method: "POST",
  });
}

// ============================================
// Provider / Model Registry API endpoints
// ============================================

import type { ProvidersResponse, ProviderModels } from "@/types/models";

export async function listProviders(): Promise<ProvidersResponse> {
  return fetchApi<ProvidersResponse>("/api/providers");
}

export async function getProviderModels(
  provider: string,
  projectId: string,
  region?: string | null
): Promise<ProviderModels> {
  const params = new URLSearchParams({ project_id: projectId });
  if (region) params.append("region", region);
  return fetchApi<ProviderModels>(
    `/api/providers/${provider}/models?${params}`
  );
}

export async function refreshProviderModels(
  provider: string,
  projectId: string,
  region?: string | null
): Promise<ProviderModels> {
  const params = new URLSearchParams({ project_id: projectId });
  if (region) params.append("region", region);
  return fetchApi<ProviderModels>(
    `/api/providers/${provider}/models/refresh?${params}`,
    { method: "POST" }
  );
}

// ============================================
// Multi-Agent (v2) API endpoints
// ============================================

export interface AgentCreatePayload {
  id: string;
  name: string;
  nodes: FlowNodeBackend[];
  edges: FlowEdge[];
  root?: string | null;
  llm: LlmBinding;
  tools_allowlist: string[];
  memory_namespace?: string | null;
  budgets: BudgetSpec;
  policies?: PolicySpec | null;
  retries?: RetrySpec | null;
  fallbacks?: FallbackSpec | null;
}

export interface AgentUpdatePayload {
  name?: string;
  nodes?: FlowNodeBackend[];
  edges?: FlowEdge[];
  root?: string | null;
  llm?: Partial<LlmBinding>;
  tools_allowlist?: string[];
  memory_namespace?: string | null;
  budgets?: Partial<BudgetSpec>;
  policies?: PolicySpec | null;
  retries?: RetrySpec | null;
  fallbacks?: FallbackSpec | null;
}

export interface HandoffCreatePayload {
  from_agent_id: string;
  to_agent_id: string;
  mode: "call" | "delegate";
  guard?: Record<string, unknown> | null;
  input_schema?: SchemaRef | null;
  output_schema?: SchemaRef | null;
}

export async function listAgents(flowId: string): Promise<AgentSpec[]> {
  return fetchApi<AgentSpec[]>(`/flows/${flowId}/agents`);
}

export async function createAgent(
  flowId: string,
  agent: AgentCreatePayload
): Promise<AgentSpec> {
  return fetchApi<AgentSpec>(`/flows/${flowId}/agents`, {
    method: "POST",
    body: JSON.stringify(agent),
  });
}

export async function updateAgent(
  flowId: string,
  agentId: string,
  data: AgentUpdatePayload
): Promise<AgentSpec> {
  return fetchApi<AgentSpec>(`/flows/${flowId}/agents/${agentId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteAgent(
  flowId: string,
  agentId: string
): Promise<void> {
  return fetchApi<void>(`/flows/${flowId}/agents/${agentId}`, {
    method: "DELETE",
  });
}

export async function listHandoffs(flowId: string): Promise<HandoffRule[]> {
  return fetchApi<HandoffRule[]>(`/flows/${flowId}/handoffs`);
}

export async function createHandoff(
  flowId: string,
  handoff: HandoffCreatePayload
): Promise<HandoffRule> {
  return fetchApi<HandoffRule>(`/flows/${flowId}/handoffs`, {
    method: "POST",
    body: JSON.stringify(handoff),
  });
}

export async function deleteHandoff(
  flowId: string,
  index: number
): Promise<void> {
  return fetchApi<void>(`/flows/${flowId}/handoffs/${index}`, {
    method: "DELETE",
  });
}

export interface IntegrationLibraryIndex {
  shared_files: string[];
  docs_files: string[];
  recipes: Record<string, string[]>;
}

export interface IntegrationLibraryFile {
  path: string;
  content: string;
}

export async function getIntegrationsLibraryIndex(): Promise<IntegrationLibraryIndex> {
  return fetchApi<IntegrationLibraryIndex>("/integrations/library");
}

export async function getIntegrationsLibraryFile(path: string): Promise<IntegrationLibraryFile> {
  const params = new URLSearchParams({ path });
  return fetchApi<IntegrationLibraryFile>(`/integrations/library/file?${params.toString()}`);
}

export async function downloadIntegrationsLibraryZip(recipe?: string): Promise<void> {
  const params = new URLSearchParams();
  if (recipe) params.append("recipe", recipe);
  const url = `${API_BASE_URL}/integrations/library/export${params.toString() ? `?${params.toString()}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText, "Failed to export integrations zip");
  }
  const blob = await response.blob();
  const cd = response.headers.get("content-disposition");
  const plain = cd?.match(/filename=\"?([^\";]+)\"?/i)?.[1];
  const filename = plain || (recipe ? `forge_integration_${recipe}.zip` : "forge_integrations_library.zip");
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  URL.revokeObjectURL(objectUrl);
  document.body.removeChild(a);
}

export { API_BASE_URL };
