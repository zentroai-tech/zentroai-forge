import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Flow, FlowNode, FlowEdge, FlowNodeBackend, EnginePreference, NodeType } from "@/types/ir";
import { DEFAULT_NODE_PARAMS } from "@/types/ir";
import { v4 as uuidv4 } from "uuid";
import type { AgentSpec, EntrypointSpec, HandoffRule, ResourceRegistry, PolicySpec } from "@/types/agents";

type AgentDraft = {
  id: string;
  name: string;
  llm?: AgentSpec["llm"];
  tools_allowlist?: string[];
  memory_namespace?: string | null;
  budgets?: AgentSpec["budgets"];
};

export type MCPServerConfig = {
  id: string;
  name: string;
  command: string;
  args: string[];
  cwd?: string;
  env?: Record<string, string>;
  timeout_seconds?: number;
};

const DEFAULT_V2_RESOURCES: ResourceRegistry = {
  shared_memory_namespaces: [],
  global_tools: [],
  schema_contracts: {},
};

const DEFAULT_POLICY_SPEC: PolicySpec = {
  tool_allowlist: [],
  tool_denylist: [],
  max_tool_calls: null,
  max_steps: null,
  max_depth: null,
  abstain: {
    enabled: true,
    reason_template: "Insufficient confidence to continue safely.",
    confidence_threshold: 0.3,
    require_citations_for_rag: false,
  },
  redaction: {
    enabled: true,
    patterns: [],
    mask: "***REDACTED***",
  },
  input_sanitization: {
    enabled: true,
    max_input_chars: 8000,
    strip_html: true,
  },
  allow_schema_soft_fail: false,
};

const STORE_VERSION = 2;
const STORE_KEY = `agent-compiler-flow-store-v${STORE_VERSION}`;

function toVisualNodeId(agentId: string, nodeId: string): string {
  return `${agentId}::${nodeId}`;
}

function fromVisualNodeId(visualId: string): { agentId: string; nodeId: string } | null {
  const separatorIndex = visualId.indexOf("::");
  if (separatorIndex <= 0) return null;
  return {
    agentId: visualId.slice(0, separatorIndex),
    nodeId: visualId.slice(separatorIndex + 2),
  };
}

function createStarterNode(nodeId: string = "output"): FlowNodeBackend {
  return {
    id: nodeId,
    type: "Output",
    name: "Output",
    params: {
      output_template: "{input}",
      format: "text",
      is_start: true,
    },
  };
}

function withSingleAgentStart(agent: AgentSpec): AgentSpec {
  if (agent.graph.nodes.length === 0) {
    const starter = createStarterNode();
    return {
      ...agent,
      graph: {
        ...agent.graph,
        nodes: [starter],
        edges: [],
        root: starter.id,
      },
    };
  }

  let startNode = agent.graph.nodes.find(
    (n) => Boolean((n.params as unknown as Record<string, unknown>)?.is_start)
  );
  if (!startNode) {
    startNode = agent.graph.nodes[0];
  }

  return {
    ...agent,
    graph: {
      ...agent.graph,
      nodes: agent.graph.nodes.map((node) => ({
        ...node,
        params: {
          ...node.params,
          is_start: node.id === startNode!.id,
        },
      })),
      root: startNode.id,
    },
  };
}

function buildCanvasFromAgents(flow: Flow): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const positionsById = new Map<string, { x: number; y: number }>();
  for (const node of flow.nodes || []) {
    positionsById.set(node.id, node.position);
  }

  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];

  (flow.agents || []).forEach((agent, agentIndex) => {
    agent.graph.nodes.forEach((node, nodeIndex) => {
      const visualId = toVisualNodeId(agent.id, node.id);
      nodes.push({
        ...node,
        id: visualId,
        position: positionsById.get(visualId) || {
          x: 120 + agentIndex * 340 + (nodeIndex % 2) * 170,
          y: 110 + Math.floor(nodeIndex / 2) * 150,
        },
      });
    });

    for (const edge of agent.graph.edges) {
      edges.push({
        source: toVisualNodeId(agent.id, edge.source),
        target: toVisualNodeId(agent.id, edge.target),
        condition: edge.condition ?? null,
      });
    }
  });

  return { nodes, edges };
}

function rebuildCanvasFromV2(flow: Flow): Flow {
  if (flow.ir_version !== "2" || !flow.agents?.length) return flow;
  const normalizedAgents = flow.agents.map(withSingleAgentStart);
  const withNormalized = { ...flow, agents: normalizedAgents };
  const { nodes, edges } = buildCanvasFromAgents(withNormalized);
  return { ...withNormalized, nodes, edges };
}

function syncV2GraphFromCanvas(flow: Flow, onlyAgentId?: string): Flow {
  if (flow.ir_version !== "2" || !flow.agents?.length) return flow;

  const updatedAgents = flow.agents.map((agent) => {
    if (onlyAgentId && agent.id !== onlyAgentId) return agent;

    const nodesForAgent = (flow.nodes || [])
      .filter((node) => fromVisualNodeId(node.id)?.agentId === agent.id)
      .map((node) => {
        const parsed = fromVisualNodeId(node.id);
        const { position, ...backendNode } = node;
        return {
          ...backendNode,
          id: parsed?.nodeId || node.id,
        } as FlowNodeBackend;
      });

    const edgesForAgent = (flow.edges || [])
      .map((edge) => {
        const parsedSource = fromVisualNodeId(edge.source);
        const parsedTarget = fromVisualNodeId(edge.target);
        if (!parsedSource || !parsedTarget) return null;
        if (parsedSource.agentId !== agent.id || parsedTarget.agentId !== agent.id) return null;
        return {
          source: parsedSource.nodeId,
          target: parsedTarget.nodeId,
          condition: edge.condition ?? null,
        };
      })
      .filter((edge): edge is NonNullable<typeof edge> => edge !== null);

    if (nodesForAgent.length === 0) {
      return agent;
    }

    return withSingleAgentStart({
      ...agent,
      graph: {
        ...agent.graph,
        nodes: nodesForAgent,
        edges: edgesForAgent,
      },
    });
  });

  return rebuildCanvasFromV2({
    ...flow,
    agents: updatedAgents,
  });
}

interface FlowStore {
  // Current flow being edited
  currentFlow: Flow | null;
  selectedNodeId: string | null;
  selectedAgentId: string | null;
  hasUnsavedChanges: boolean;
  mcpServers: MCPServerConfig[];

  // Ephemeral UI state (not persisted)
  navRailPanel: "flows" | "settings" | null;
  bottomDockGroup: "run" | "test" | "code" | null;
  bottomDockTab: string | undefined;

  // Actions
  setCurrentFlow: (flow: Flow | null) => void;
  createNewFlow: (name?: string) => void;
  updateFlowMeta: (updates: Partial<Pick<Flow, "name" | "version" | "engine_preference" | "description">>) => void;
  setSelectedAgentId: (agentId: string | null) => void;
  addAgent: (draft: AgentDraft) => AgentSpec | null;
  updateAgentMeta: (agentId: string, patch: Partial<Omit<AgentSpec, "id" | "graph">>) => AgentSpec | null;
  removeAgent: (agentId: string) => boolean;
  setEntrypoints: (entrypoints: EntrypointSpec[]) => void;
  setFlowPolicies: (policies: PolicySpec) => void;
  setSchemaContracts: (schemas: Record<string, Record<string, unknown>>) => void;
  setHandoffs: (handoffs: HandoffRule[]) => void;
  addHandoff: (handoff: HandoffRule) => boolean;
  removeHandoff: (index: number) => void;
  syncV2GraphFromCanvas: (agentId?: string) => void;
  rebuildCanvasFromV2: () => void;
  setMcpServers: (servers: MCPServerConfig[]) => void;
  addMcpServer: (server: MCPServerConfig) => boolean;
  updateMcpServer: (serverId: string, patch: Partial<MCPServerConfig>) => boolean;
  removeMcpServer: (serverId: string) => void;

  // Node operations
  addNode: (type: NodeType, position: { x: number; y: number }) => string;
  updateNode: (nodeId: string, updates: Partial<FlowNode>) => void;
  removeNode: (nodeId: string) => void;
  selectNode: (nodeId: string | null) => void;

  // Edge operations
  addEdge: (source: string, target: string, condition?: string) => string;
  updateEdge: (edgeId: string, updates: Partial<FlowEdge>) => void;
  removeEdge: (edgeId: string) => void;

  // Sync state
  markSaved: () => void;
  setUnsavedChanges: (value: boolean) => void;

  // Batch operations for React Flow
  setNodes: (nodes: FlowNode[]) => void;
  setEdges: (edges: FlowEdge[]) => void;

  // Ephemeral UI actions
  setNavRailPanel: (panel: "flows" | "settings" | null) => void;
  openBottomDock: (group: "run" | "test" | "code", tab?: string) => void;
  closeBottomDock: () => void;
  setBottomDockTab: (tab: string) => void;
}

function createEmptyFlow(name: string = "Untitled Flow"): Flow {
  const starter = createStarterNode("start");
  const mainAgent: AgentSpec = withSingleAgentStart({
    id: "main",
    name: "Main Agent",
    graph: {
      nodes: [starter],
      edges: [],
      root: starter.id,
    },
    llm: {
      provider: "auto",
      model: "gpt-4o-mini",
      temperature: 0.7,
      system_prompt: null,
    },
    tools_allowlist: [],
    memory_namespace: "main_memory",
    budgets: {
      max_tokens: null,
      max_tool_calls: null,
      max_steps: null,
      max_depth: 5,
    },
  });
  const baseFlow: Flow = {
    id: uuidv4(),
    name,
    version: "1.0.0",
    description: "",
    ir_version: "2",
    engine_preference: "langchain",
    nodes: [],
    edges: [],
    agents: [mainAgent],
    handoffs: [],
    entrypoints: [{ name: "main", agent_id: "main", description: "Default entrypoint" }],
    resources: DEFAULT_V2_RESOURCES,
    policies: DEFAULT_POLICY_SPEC,
  };
  return rebuildCanvasFromV2(baseFlow);
}

// Validate and fix potentially corrupted flow data from storage
function validateFlow(flow: unknown): Flow | null {
  if (!flow || typeof flow !== "object") return null;

  const f = flow as Record<string, unknown>;
  const irVersion = typeof f.ir_version === "string" ? f.ir_version : "2";
  const agents = Array.isArray(f.agents) ? (f.agents as AgentSpec[]) : undefined;
  const handoffs = Array.isArray(f.handoffs) ? (f.handoffs as HandoffRule[]) : undefined;
  const entrypoints = Array.isArray(f.entrypoints) ? (f.entrypoints as EntrypointSpec[]) : undefined;
  const resources = (f.resources && typeof f.resources === "object")
    ? ({
        ...DEFAULT_V2_RESOURCES,
        ...(f.resources as ResourceRegistry),
        schema_contracts: ((f.resources as ResourceRegistry).schema_contracts || {}),
      } as ResourceRegistry)
    : undefined;
  const policies = (f.policies && typeof f.policies === "object")
    ? (f.policies as PolicySpec)
    : undefined;

  // Ensure required fields exist with proper defaults
  const validated: Flow = {
    id: typeof f.id === "string" ? f.id : uuidv4(),
    name: typeof f.name === "string" ? f.name : "Untitled Flow",
    version: typeof f.version === "string" ? f.version : "1.0.0",
    description: typeof f.description === "string" ? f.description : "",
    ir_version: irVersion,
    engine_preference: ["langchain", "llamaindex", "auto"].includes(f.engine_preference as string)
      ? (f.engine_preference as EnginePreference)
      : "langchain",
    nodes: Array.isArray(f.nodes) ? f.nodes : [],
    edges: Array.isArray(f.edges) ? f.edges : [],
    agents,
    handoffs,
    entrypoints,
    resources,
    policies,
    created_at: typeof f.created_at === "string" ? f.created_at : undefined,
    updated_at: typeof f.updated_at === "string" ? f.updated_at : undefined,
  };
  return rebuildCanvasFromV2(validated);
}

function validateMcpServers(servers: unknown): MCPServerConfig[] {
  if (!Array.isArray(servers)) return [];
  return servers
    .filter((server): server is MCPServerConfig => {
      if (!server || typeof server !== "object") return false;
      const s = server as Record<string, unknown>;
      return (
        typeof s.id === "string" &&
        typeof s.name === "string" &&
        typeof s.command === "string" &&
        Array.isArray(s.args)
      );
    })
    .map((server) => ({
      ...server,
      args: server.args.map((arg) => String(arg)),
    }));
}

export const useFlowStore = create<FlowStore>()(
  persist(
    (set, get) => ({
      currentFlow: null,
      selectedNodeId: null,
      selectedAgentId: null,
      hasUnsavedChanges: false,
      mcpServers: [],

      // Ephemeral UI state
      navRailPanel: null,
      bottomDockGroup: null,
      bottomDockTab: undefined,

      setCurrentFlow: (flow) => {
        const hydratedFlow = flow
          ? ({
              ...rebuildCanvasFromV2(flow),
              policies: flow.policies || DEFAULT_POLICY_SPEC,
              resources: {
                ...DEFAULT_V2_RESOURCES,
                ...(flow.resources || {}),
                schema_contracts: flow.resources?.schema_contracts || {},
              },
            } as Flow)
          : null;
        const agentId = hydratedFlow?.agents?.[0]?.id ?? null;
        set({ currentFlow: hydratedFlow, selectedNodeId: null, selectedAgentId: agentId, hasUnsavedChanges: false });
      },

      setSelectedAgentId: (agentId) => {
        set({ selectedAgentId: agentId, selectedNodeId: null });
      },

      addAgent: (draft) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return null;
        const agents = currentFlow.agents || [];
        if (agents.some((agent) => agent.id === draft.id)) return null;

        const newAgent = withSingleAgentStart({
          id: draft.id,
          name: draft.name,
          graph: { nodes: [createStarterNode("start")], edges: [], root: "start" },
          llm: draft.llm || {
            provider: "auto",
            model: "gpt-4o-mini",
            temperature: 0.7,
            system_prompt: null,
          },
          tools_allowlist: draft.tools_allowlist || [],
          memory_namespace: draft.memory_namespace || `${draft.id}_memory`,
          budgets: draft.budgets || {
            max_tokens: null,
            max_tool_calls: null,
            max_steps: null,
            max_depth: 5,
          },
        });

        const updatedFlow = rebuildCanvasFromV2({
          ...currentFlow,
          agents: [...agents, newAgent],
          resources: currentFlow.resources || DEFAULT_V2_RESOURCES,
        });

        set({
          currentFlow: updatedFlow,
          selectedAgentId: newAgent.id,
          selectedNodeId: null,
          hasUnsavedChanges: true,
        });
        return newAgent;
      },

      updateAgentMeta: (agentId, patch) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2" || !currentFlow.agents) return null;

        let updatedAgent: AgentSpec | null = null;
        const updatedAgents = currentFlow.agents.map((agent) => {
          if (agent.id !== agentId) return agent;
          updatedAgent = {
            ...agent,
            ...patch,
            graph: agent.graph,
            id: agent.id,
          };
          return updatedAgent;
        });

        if (!updatedAgent) return null;

        set({
          currentFlow: {
            ...currentFlow,
            agents: updatedAgents,
          },
          hasUnsavedChanges: true,
        });
        return updatedAgent;
      },

      removeAgent: (agentId) => {
        const { currentFlow, selectedAgentId } = get();
        if (!currentFlow || currentFlow.ir_version !== "2" || !currentFlow.agents) return false;
        if (currentFlow.agents.length <= 1) return false;

        const agents = currentFlow.agents.filter((agent) => agent.id !== agentId);
        const handoffs = (currentFlow.handoffs || []).filter(
          (handoff) => handoff.from_agent_id !== agentId && handoff.to_agent_id !== agentId
        );
        let entrypoints = (currentFlow.entrypoints || []).filter((entry) => entry.agent_id !== agentId);
        if (entrypoints.length === 0) {
          entrypoints = [{ name: "main", agent_id: agents[0].id, description: "Default entrypoint" }];
        }

        const rebuilt = rebuildCanvasFromV2({
          ...currentFlow,
          agents,
          handoffs,
          entrypoints,
          resources: currentFlow.resources || DEFAULT_V2_RESOURCES,
        });

        set({
          currentFlow: rebuilt,
          selectedAgentId: selectedAgentId === agentId ? agents[0].id : selectedAgentId,
          selectedNodeId: null,
          hasUnsavedChanges: true,
        });
        return true;
      },

      setEntrypoints: (entrypoints) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return;
        set({
          currentFlow: { ...currentFlow, entrypoints },
          hasUnsavedChanges: true,
        });
      },

      setFlowPolicies: (policies) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return;
        set({
          currentFlow: { ...currentFlow, policies },
          hasUnsavedChanges: true,
        });
      },

      setSchemaContracts: (schemas) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return;
        const resources = currentFlow.resources || DEFAULT_V2_RESOURCES;
        set({
          currentFlow: {
            ...currentFlow,
            resources: {
              ...resources,
              schema_contracts: schemas,
            },
          },
          hasUnsavedChanges: true,
        });
      },

      setHandoffs: (handoffs) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return;
        set({
          currentFlow: { ...currentFlow, handoffs },
          hasUnsavedChanges: true,
        });
      },

      addHandoff: (handoff) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return false;
        if (handoff.from_agent_id === handoff.to_agent_id) return false;
        const exists = (currentFlow.handoffs || []).some(
          (h) => h.from_agent_id === handoff.from_agent_id
            && h.to_agent_id === handoff.to_agent_id
            && h.mode === handoff.mode
        );
        if (exists) return false;
        set({
          currentFlow: {
            ...currentFlow,
            handoffs: [...(currentFlow.handoffs || []), handoff],
          },
          hasUnsavedChanges: true,
        });
        return true;
      },

      removeHandoff: (index) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return;
        set({
          currentFlow: {
            ...currentFlow,
            handoffs: (currentFlow.handoffs || []).filter((_, i) => i !== index),
          },
          hasUnsavedChanges: true,
        });
      },

      syncV2GraphFromCanvas: (agentId) => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return;
        const synced = syncV2GraphFromCanvas(currentFlow, agentId);
        set({ currentFlow: synced, hasUnsavedChanges: true });
      },

      rebuildCanvasFromV2: () => {
        const { currentFlow } = get();
        if (!currentFlow || currentFlow.ir_version !== "2") return;
        set({
          currentFlow: rebuildCanvasFromV2(currentFlow),
        });
      },

      setMcpServers: (servers) => {
        set({ mcpServers: servers });
      },

      addMcpServer: (server) => {
        const { mcpServers } = get();
        if (mcpServers.some((s) => s.id === server.id)) return false;
        set({ mcpServers: [...mcpServers, server] });
        return true;
      },

      updateMcpServer: (serverId, patch) => {
        const { mcpServers } = get();
        if (!mcpServers.some((s) => s.id === serverId)) return false;
        set({
          mcpServers: mcpServers.map((server) =>
            server.id === serverId ? { ...server, ...patch, id: server.id } : server
          ),
        });
        return true;
      },

      removeMcpServer: (serverId) => {
        const { mcpServers } = get();
        set({ mcpServers: mcpServers.filter((server) => server.id !== serverId) });
      },

      createNewFlow: (name) => {
        set({
          currentFlow: createEmptyFlow(name),
          selectedNodeId: null,
          hasUnsavedChanges: true
        });
      },

      updateFlowMeta: (updates) => {
        const { currentFlow } = get();
        if (!currentFlow) return;
        set({
          currentFlow: { ...currentFlow, ...updates },
          hasUnsavedChanges: true,
        });
      },

      addNode: (type, position) => {
        const { currentFlow, selectedAgentId } = get();
        if (!currentFlow) return "";

        if (currentFlow.ir_version === "2" && currentFlow.agents?.length) {
          const targetAgentId = selectedAgentId || currentFlow.agents[0].id;
          const targetAgent = currentFlow.agents.find((agent) => agent.id === targetAgentId);
          if (!targetAgent) return "";

          const newNodeId = `node_${uuidv4().slice(0, 8)}`;
          const newBackendNode: FlowNodeBackend = {
            id: newNodeId,
            type,
            name: `${type} Node`,
            params: {
              ...DEFAULT_NODE_PARAMS[type],
              is_start: targetAgent.graph.nodes.length === 0,
            },
          };

          const updatedAgents = currentFlow.agents.map((agent) => {
            if (agent.id !== targetAgentId) return agent;
            return withSingleAgentStart({
              ...agent,
              graph: {
                ...agent.graph,
                nodes: [...agent.graph.nodes, newBackendNode],
              },
            });
          });

          const updated = rebuildCanvasFromV2({
            ...currentFlow,
            agents: updatedAgents,
          });

          const visualId = toVisualNodeId(targetAgentId, newNodeId);
          const positionedNodes = updated.nodes.map((node) =>
            node.id === visualId ? { ...node, position } : node
          );

          set({
            currentFlow: syncV2GraphFromCanvas({ ...updated, nodes: positionedNodes }),
            selectedAgentId: targetAgentId,
            hasUnsavedChanges: true,
          });
          return visualId;
        }

        const nodeId = uuidv4();
        const newNode: FlowNode = {
          id: nodeId,
          type,
          name: `${type} Node`,
          params: { ...DEFAULT_NODE_PARAMS[type] },
          position,
        };

        // If this is the first node, mark it as start
        const nodes = currentFlow.nodes || [];
        if (nodes.length === 0) {
          (newNode.params as unknown as Record<string, unknown>).is_start = true;
        }

        set({
          currentFlow: {
            ...currentFlow,
            nodes: [...nodes, newNode],
          },
          hasUnsavedChanges: true,
        });

        return nodeId;
      },

      updateNode: (nodeId, updates) => {
        const { currentFlow } = get();
        if (!currentFlow) return;

        if (currentFlow.ir_version === "2" && currentFlow.agents?.length) {
          const parsed = fromVisualNodeId(nodeId);
          if (!parsed) return;

          const updatedAgents = currentFlow.agents.map((agent) => {
            if (agent.id !== parsed.agentId) return agent;

            const startToggle =
              updates.params &&
              Object.prototype.hasOwnProperty.call(updates.params as Record<string, unknown>, "is_start")
                ? Boolean((updates.params as Record<string, unknown>).is_start)
                : undefined;

            let updatedNodes = agent.graph.nodes.map((node) => {
              const isTarget = node.id === parsed.nodeId;
              const nextNode = isTarget
                ? ({
                    ...node,
                    ...(updates.name ? { name: updates.name } : {}),
                    ...(updates.type ? { type: updates.type } : {}),
                    ...(updates.params ? { params: updates.params } : {}),
                  } as FlowNodeBackend)
                : node;

              if (startToggle === true) {
                return {
                  ...nextNode,
                  params: {
                    ...nextNode.params,
                    is_start: isTarget,
                  },
                } as FlowNodeBackend;
              }

              if (startToggle === false && isTarget) {
                return {
                  ...nextNode,
                  params: {
                    ...nextNode.params,
                    is_start: false,
                  },
                } as FlowNodeBackend;
              }

              return nextNode;
            });

            if (startToggle === false) {
              const hasAnyStart = updatedNodes.some(
                (node) => Boolean((node.params as Record<string, unknown>)?.is_start)
              );
              if (!hasAnyStart) {
                const fallbackIndex = updatedNodes.findIndex((node) => node.id !== parsed.nodeId);
                if (fallbackIndex >= 0) {
                  const fallbackNode = updatedNodes[fallbackIndex];
                  updatedNodes[fallbackIndex] = {
                    ...fallbackNode,
                    params: {
                      ...fallbackNode.params,
                      is_start: true,
                    },
                  } as FlowNodeBackend;
                } else if (updatedNodes.length > 0) {
                  const onlyNode = updatedNodes[0];
                  updatedNodes[0] = {
                    ...onlyNode,
                    params: {
                      ...onlyNode.params,
                      is_start: true,
                    },
                  } as FlowNodeBackend;
                }
              }
            }

            return withSingleAgentStart({
              ...agent,
              graph: {
                ...agent.graph,
                nodes: updatedNodes,
              },
            });
          });

          const rebuilt = rebuildCanvasFromV2({
            ...currentFlow,
            agents: updatedAgents,
          });

          const mergedNodes = rebuilt.nodes.map((node) =>
            node.id === nodeId ? { ...node, ...updates } : node
          );

          set({
            currentFlow: syncV2GraphFromCanvas({ ...rebuilt, nodes: mergedNodes }, parsed.agentId),
            hasUnsavedChanges: true,
          });
          return;
        }

        set({
          currentFlow: {
            ...currentFlow,
            nodes: (currentFlow.nodes || []).map((node) =>
              node.id === nodeId ? { ...node, ...updates } : node
            ),
          },
          hasUnsavedChanges: true,
        });
      },

      removeNode: (nodeId) => {
        const { currentFlow, selectedNodeId, selectedAgentId } = get();
        if (!currentFlow) return;

        if (currentFlow.ir_version === "2" && currentFlow.agents?.length) {
          const parsed = fromVisualNodeId(nodeId);
          if (!parsed) return;

          const updatedAgents = currentFlow.agents.map((agent) => {
            if (agent.id !== parsed.agentId) return agent;
            const remainingNodes = agent.graph.nodes.filter((node) => node.id !== parsed.nodeId);
            const remainingEdges = agent.graph.edges.filter(
              (edge) => edge.source !== parsed.nodeId && edge.target !== parsed.nodeId
            );

            return withSingleAgentStart({
              ...agent,
              graph: {
                ...agent.graph,
                nodes: remainingNodes,
                edges: remainingEdges,
              },
            });
          });

          const rebuilt = rebuildCanvasFromV2({
            ...currentFlow,
            agents: updatedAgents,
          });

          set({
            currentFlow: rebuilt,
            selectedNodeId: selectedNodeId === nodeId ? null : selectedNodeId,
            selectedAgentId: selectedAgentId || parsed.agentId,
            hasUnsavedChanges: true,
          });
          return;
        }

        set({
          currentFlow: {
            ...currentFlow,
            nodes: (currentFlow.nodes || []).filter((n) => n.id !== nodeId),
            // Also remove connected edges
            edges: (currentFlow.edges || []).filter(
              (e) => e.source !== nodeId && e.target !== nodeId
            ),
          },
          selectedNodeId: selectedNodeId === nodeId ? null : selectedNodeId,
          hasUnsavedChanges: true,
        });
      },

      selectNode: (nodeId) => {
        set({ selectedNodeId: nodeId });
      },

      addEdge: (source, target, condition) => {
        const { currentFlow } = get();
        if (!currentFlow) return "";

        if (currentFlow.ir_version === "2" && currentFlow.agents?.length) {
          const parsedSource = fromVisualNodeId(source);
          const parsedTarget = fromVisualNodeId(target);
          if (!parsedSource || !parsedTarget) return "";
          if (parsedSource.agentId !== parsedTarget.agentId) return "";

          const agentId = parsedSource.agentId;
          const updatedAgents = currentFlow.agents.map((agent) => {
            if (agent.id !== agentId) return agent;
            const exists = agent.graph.edges.some(
              (edge) => edge.source === parsedSource.nodeId && edge.target === parsedTarget.nodeId
            );
            if (exists) return agent;
            return {
              ...agent,
              graph: {
                ...agent.graph,
                edges: [
                  ...agent.graph.edges,
                  {
                    source: parsedSource.nodeId,
                    target: parsedTarget.nodeId,
                    condition: condition || null,
                  },
                ],
              },
            };
          });

          const rebuilt = rebuildCanvasFromV2({
            ...currentFlow,
            agents: updatedAgents,
          });

          set({
            currentFlow: rebuilt,
            hasUnsavedChanges: true,
          });
          return `${source}-${target}`;
        }

        const edges = currentFlow.edges || [];

        // Prevent duplicate edges and self-loops
        if (source === target) return "";
        const exists = edges.some(
          (e) => e.source === source && e.target === target
        );
        if (exists) return "";

        const newEdge: FlowEdge = {
          source,
          target,
          condition: condition || null,
        };

        set({
          currentFlow: {
            ...currentFlow,
            edges: [...edges, newEdge],
          },
          hasUnsavedChanges: true,
        });

        return `${source}-${target}`;
      },

      updateEdge: (edgeId, updates) => {
        const { currentFlow } = get();
        if (!currentFlow) return;
        const updatedEdges = (currentFlow.edges || []).map((edge) => {
          const id = `${edge.source}-${edge.target}`;
          return id === edgeId ? { ...edge, ...updates } : edge;
        });
        let nextFlow: Flow = { ...currentFlow, edges: updatedEdges };
        if (currentFlow.ir_version === "2") {
          nextFlow = syncV2GraphFromCanvas(nextFlow);
        }
        set({ currentFlow: nextFlow, hasUnsavedChanges: true });
      },

      removeEdge: (edgeId) => {
        const { currentFlow } = get();
        if (!currentFlow) return;
        const filtered = (currentFlow.edges || []).filter((edge) => `${edge.source}-${edge.target}` !== edgeId);
        let nextFlow: Flow = { ...currentFlow, edges: filtered };
        if (currentFlow.ir_version === "2") {
          nextFlow = syncV2GraphFromCanvas(nextFlow);
        }
        set({ currentFlow: nextFlow, hasUnsavedChanges: true });
      },

      markSaved: () => {
        set({ hasUnsavedChanges: false });
      },

      setUnsavedChanges: (value) => {
        set({ hasUnsavedChanges: value });
      },

      setNodes: (nodes) => {
        const { currentFlow } = get();
        if (!currentFlow) return;
        let nextFlow: Flow = { ...currentFlow, nodes };
        if (currentFlow.ir_version === "2") {
          nextFlow = syncV2GraphFromCanvas(nextFlow);
        }
        set({
          currentFlow: nextFlow,
          hasUnsavedChanges: true,
        });
      },

      setEdges: (edges) => {
        const { currentFlow } = get();
        if (!currentFlow) return;
        let nextFlow: Flow = { ...currentFlow, edges };
        if (currentFlow.ir_version === "2") {
          nextFlow = syncV2GraphFromCanvas(nextFlow);
        }
        set({
          currentFlow: nextFlow,
          hasUnsavedChanges: true,
        });
      },

      // Ephemeral UI actions
      setNavRailPanel: (panel) => set({ navRailPanel: panel }),
      openBottomDock: (group, tab) => set({ bottomDockGroup: group, bottomDockTab: tab }),
      closeBottomDock: () => set({ bottomDockGroup: null, bottomDockTab: undefined }),
      setBottomDockTab: (tab) => set({ bottomDockTab: tab }),
    }),
    {
      name: STORE_KEY,
      partialize: (state) => ({
        currentFlow: state.currentFlow,
        hasUnsavedChanges: state.hasUnsavedChanges,
        mcpServers: state.mcpServers,
      }),
      onRehydrateStorage: () => (state) => {
        // Validate and fix the rehydrated flow data
        if (state?.currentFlow) {
          state.currentFlow = validateFlow(state.currentFlow);
        }
        if (state) {
          state.mcpServers = validateMcpServers(state.mcpServers);
        }
      },
    }
  )
);
