"use client";

import { useCallback, useRef, DragEvent, useMemo, useEffect, useState } from "react";
import toast from "react-hot-toast";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type Connection,
  type OnNodesChange,
  type OnEdgesChange,
  MarkerType,
  BackgroundVariant,
} from "reactflow";
import "reactflow/dist/style.css";

import { useFlowStore } from "@/lib/store";
import CustomNode from "./CustomNode";
import AgentSelector from "./AgentSelector";
import AgentConfigModal from "./AgentConfigModal";
import { createAgent, deleteAgent, updateAgent } from "@/lib/api";
import { NODE_TYPE_COLORS, type NodeType, type FlowNode, type FlowEdge } from "@/types/ir";
import type { AgentSpec } from "@/types/agents";

const nodeTypes = {
  custom: CustomNode,
};

const AGENT_COLORS = [
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#f59e0b", // amber
  "#10b981", // emerald
  "#ef4444", // red
  "#ec4899", // pink
  "#3b82f6", // blue
  "#f97316", // orange
];

type SystemConfigTarget = "policies" | "retry_fallback" | "schemas" | "ir_json";

const SYSTEM_CONFIG_GHOSTS: Array<{
  id: SystemConfigTarget;
  label: string;
  description: string;
  color: string;
  icon: React.ReactNode;
}> = [
  {
    id: "policies",
    label: "Policy Guard",
    description: "Allow/Deny, redaction, sanitization",
    color: "#64748B",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
  {
    id: "retry_fallback",
    label: "Retry/Fallback",
    description: "Attempts, backoff, fallback chains",
    color: "#8FA0B5",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12a9 9 0 0 1-15.5 6.3" />
        <path d="M3 12A9 9 0 0 1 18.5 5.7" />
        <path d="M3 17v-4h4" />
        <path d="M21 7v4h-4" />
      </svg>
    ),
  },
  {
    id: "schemas",
    label: "Schema Validate",
    description: "Input/output contracts for handoffs",
    color: "#7D92AA",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16v16H4z" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </svg>
    ),
  },
  {
    id: "ir_json",
    label: "IR JSON",
    description: "Browse the exact serialized project IR",
    color: "#94A3B8",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M8 6H4v12h4" />
        <path d="M16 6h4v12h-4" />
        <path d="M10 9l4 6" />
        <path d="M14 9l-4 6" />
      </svg>
    ),
  },
];

export default function FlowCanvas() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const {
    currentFlow,
    selectedNodeId,
    selectedAgentId,
    setSelectedAgentId,
    addNode,
    selectNode,
    addEdge: storeAddEdge,
    updateNode,
    removeNode,
    removeEdge,
    addAgent: storeAddAgent,
    updateAgentMeta,
    removeAgent: storeRemoveAgent,
    setCurrentFlow,
  } = useFlowStore();
  const [isAgentModalOpen, setIsAgentModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentSpec | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const isV2 = currentFlow?.agents && currentFlow.agents.length > 0;
  const getOwnerAgentId = useCallback((node: FlowNode): string | undefined => {
    if (!isV2) return undefined;
    const separatorIndex = node.id.indexOf("::");
    if (separatorIndex <= 0) return undefined;
    return node.id.slice(0, separatorIndex);
  }, [isV2]);

  // Build node-to-agent mapping for v2 flows
  const nodeAgentMap = useMemo(() => {
    const map = new Map<string, string>();
    if (currentFlow?.nodes) {
      for (const node of currentFlow.nodes) {
        const owner = getOwnerAgentId(node);
        if (owner) {
          map.set(node.id, owner);
        }
      }
    }
    return map;
  }, [currentFlow?.nodes, getOwnerAgentId]);

  // Handler for deleting a node
  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      if (confirm("Delete this node?")) {
        removeNode(nodeId);
      }
    },
    [removeNode]
  );

  // Build agent index for color assignment
  const agentColorMap = useMemo(() => {
    const map = new Map<string, string>();
    if (currentFlow?.agents) {
      currentFlow.agents.forEach((agent, i) => {
        map.set(agent.id, AGENT_COLORS[i % AGENT_COLORS.length]);
      });
    }
    return map;
  }, [currentFlow?.agents]);

  // Convert store nodes to React Flow nodes with delete handler
  const toReactFlowNodes = useCallback(
    (nodes: FlowNode[], selectedId: string | null): Node[] => {
      return nodes.map((node) => {
        const agentId = nodeAgentMap.get(node.id);
        const agentColor = agentId ? agentColorMap.get(agentId) : undefined;
        return {
          id: node.id,
          type: "custom",
          position: node.position,
          data: {
            label: node.name,
            type: node.type,
            selected: node.id === selectedId,
            onDelete: handleDeleteNode,
            agentColor,
          },
          selected: node.id === selectedId,
        };
      });
    },
    [handleDeleteNode, nodeAgentMap, agentColorMap]
  );

  // Convert store edges to React Flow edges with animated dashed style
  const toReactFlowEdges = useCallback((edges: FlowEdge[]): Edge[] => {
    return edges.map((edge) => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      label: edge.condition || undefined,
      type: "smoothstep",
      animated: false,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 14,
        height: 14,
        color: "#545d68",
      },
      style: {
        strokeWidth: 1.5,
        stroke: "#545d68",
        cursor: "pointer",
      },
      interactionWidth: 24,
      labelStyle: {
        fill: "#8b949e",
        fontWeight: 500,
        fontSize: 10,
        backgroundColor: "#0c0e12",
        padding: "1px 5px",
        borderRadius: "4px",
      },
      labelBgStyle: {
        fill: "#0c0e12",
        fillOpacity: 0.9,
      },
    }));
  }, []);

  // Memoize the conversion to prevent unnecessary re-renders
  const flowNodes = currentFlow?.nodes;
  const flowEdges = currentFlow?.edges;
  const nodeById = useMemo(() => {
    const map = new Map<string, FlowNode>();
    if (!flowNodes) return map;
    for (const node of flowNodes) {
      map.set(node.id, node);
    }
    return map;
  }, [flowNodes]);

  // Filter nodes by selected agent for v2 flows
  const filteredNodes = useMemo(() => {
    if (!flowNodes) return [];
    if (!isV2 || !selectedAgentId) return flowNodes;
    return flowNodes.filter((node) => getOwnerAgentId(node) === selectedAgentId);
  }, [flowNodes, isV2, selectedAgentId, getOwnerAgentId]);

  const filteredNodeIds = useMemo(
    () => new Set(filteredNodes.map((n) => n.id)),
    [filteredNodes]
  );

  const nodes = useMemo(() => {
    return toReactFlowNodes(filteredNodes, selectedNodeId);
  }, [filteredNodes, selectedNodeId, toReactFlowNodes]);

  const edges = useMemo(() => {
    if (!flowEdges) return [];
    const visibleEdges = isV2 && selectedAgentId
      ? flowEdges.filter((e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target))
      : flowEdges;
    return toReactFlowEdges(visibleEdges);
  }, [flowEdges, toReactFlowEdges, isV2, selectedAgentId, filteredNodeIds]);

  const validationIssues = useMemo(() => {
    if (!filteredNodes.length || !flowEdges?.length) return [];
    const visibleNodeIds = new Set(filteredNodes.map((node) => node.id));
    const visibleEdges = flowEdges.filter(
      (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)
    );

    return filteredNodes.flatMap((node) => {
      if (node.type !== "Join") return [];
      const incoming = visibleEdges.filter((edge) => edge.target === node.id).length;
      if (incoming < 2) {
        return [`Join "${node.name}" requiere al menos 2 entradas (actual: ${incoming}).`];
      }
      return [];
    });
  }, [filteredNodes, flowEdges]);

  const validateConnection = useCallback((connection: Connection): string | null => {
    const source = connection.source;
    const target = connection.target;
    if (!source || !target) return "Conexion incompleta.";
    if (source === target) return "No se permite auto-conexion.";

    if (isV2) {
      const sourceAgent = source.split("::")[0];
      const targetAgent = target.split("::")[0];
      if (sourceAgent !== targetAgent) {
        return "Cross-agent links no permitidos. Usa handoffs.";
      }
    }

    const allEdges = flowEdges || [];
    const duplicate = allEdges.some((edge) => edge.source === source && edge.target === target);
    if (duplicate) return "La conexion ya existe.";

    const sourceNode = nodeById.get(source);
    const targetNode = nodeById.get(target);
    if (!sourceNode || !targetNode) return "Nodo origen/destino invalido.";

    const outgoingFromSource = allEdges.filter((edge) => edge.source === source).length;
    const incomingToTarget = allEdges.filter((edge) => edge.target === target).length;

    if (sourceNode.type === "Join" && outgoingFromSource >= 1) {
      return "Join solo debe tener 1 salida.";
    }
    if (targetNode.type === "Parallel" && incomingToTarget >= 1) {
      return "Parallel solo debe tener 1 entrada.";
    }

    return null;
  }, [flowEdges, isV2, nodeById]);

  useEffect(() => {
    if (!isV2 || !currentFlow?.agents?.length) return;
    if (!selectedAgentId) {
      setSelectedAgentId(currentFlow.agents[0].id);
    }
  }, [currentFlow?.agents, isV2, selectedAgentId, setSelectedAgentId]);

  // Keyboard delete handler
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.key === "Delete" || event.key === "Backspace") && selectedNodeId) {
        // Don't delete if user is typing in an input
        const target = event.target as HTMLElement;
        if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
          return;
        }
        event.preventDefault();
        if (confirm("Delete this node?")) {
          removeNode(selectedNodeId);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedNodeId, removeNode]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => {
      if (!currentFlow) return;

      // Handle selection changes
      changes.forEach((change) => {
        if (change.type === "select" && change.selected) {
          selectNode(change.id);
        }
      });

      // Handle position changes
      changes.forEach((change) => {
        if (change.type === "position" && change.position) {
          updateNode(change.id, { position: change.position });
        }
      });

      // Handle node removals from React Flow
      changes.forEach((change) => {
        if (change.type === "remove") {
          removeNode(change.id);
        }
      });
    },
    [currentFlow, selectNode, updateNode, removeNode]
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      if (!currentFlow) return;

      changes.forEach((change) => {
        if (change.type === "remove") {
          removeEdge(change.id);
        }
      });
    },
    [currentFlow, removeEdge]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (connection.source && connection.target) {
        const error = validateConnection(connection);
        if (error) {
          setConnectionError(error);
          toast.error(error);
          return;
        }
        setConnectionError(null);
        storeAddEdge(connection.source, connection.target);
      }
    },
    [storeAddEdge, validateConnection]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectNode(node.id);
    },
    [selectNode]
  );

  const onNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      event.preventDefault();
      selectNode(node.id);
      if (confirm("Delete this node?")) {
        removeNode(node.id);
      }
    },
    [removeNode, selectNode]
  );

  const onEdgeClick = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      event.preventDefault();
      event.stopPropagation();
      if (confirm("Delete this connection?")) {
        removeEdge(edge.id);
      }
    },
    [removeEdge]
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
    setConnectionError(null);
  }, [selectNode]);

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData("application/reactflow") as NodeType;
      if (!type || !reactFlowWrapper.current) return;
      if (isV2 && !selectedAgentId) {
        toast.error("Select an agent before adding nodes.");
        return;
      }

      const bounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = {
        x: event.clientX - bounds.left - 75,
        y: event.clientY - bounds.top - 25,
      };

      const nodeId = addNode(type, position);
      if (nodeId) {
        selectNode(nodeId);
      }
    },
    [addNode, selectNode, isV2, selectedAgentId]
  );

  const buildAgentPayload = useCallback((agent: AgentSpec) => {
    return {
      id: agent.id,
      name: agent.name,
      nodes: agent.graph.nodes,
      edges: agent.graph.edges,
      root: agent.graph.root,
      llm: agent.llm,
      tools_allowlist: agent.tools_allowlist,
      memory_namespace: agent.memory_namespace || null,
      budgets: agent.budgets,
      policies: agent.policies || null,
      retries: agent.retries || null,
      fallbacks: agent.fallbacks || null,
    };
  }, []);

  const handleSaveAgent = useCallback(async (data: {
    id: string;
    name: string;
    llm: Partial<AgentSpec["llm"]>;
    tools_allowlist: string[];
    memory_namespace: string | null;
    budgets: Partial<AgentSpec["budgets"]>;
  }): Promise<boolean> => {
    if (!currentFlow) return false;

    const isNew = !editingAgent;
    if (isNew) {
      const added = storeAddAgent({
        id: data.id,
        name: data.name,
        llm: {
          provider: data.llm.provider || "auto",
          model: data.llm.model || "gpt-4o-mini",
          temperature: data.llm.temperature ?? 0.7,
          system_prompt: data.llm.system_prompt ?? null,
        },
        tools_allowlist: data.tools_allowlist,
        memory_namespace: data.memory_namespace,
        budgets: {
          max_tokens: data.budgets.max_tokens ?? null,
          max_tool_calls: data.budgets.max_tool_calls ?? null,
          max_steps: data.budgets.max_steps ?? null,
          max_depth: data.budgets.max_depth ?? 5,
        },
      });
      if (!added) {
        toast.error("Agent ID already exists or flow is not multi-agent.");
        return false;
      }

      if (currentFlow.created_at) {
        try {
          await createAgent(currentFlow.id, buildAgentPayload(added));
        } catch (error) {
          storeRemoveAgent(added.id);
          toast.error(error instanceof Error ? error.message : "Failed to persist agent");
          return false;
        }
      }
      toast.success("Agent created");
      return true;
    }

    if (!editingAgent) return false;
    const snapshot = currentFlow;
    const updated = updateAgentMeta(editingAgent.id, {
      name: data.name,
      llm: {
        ...editingAgent.llm,
        ...data.llm,
      },
      tools_allowlist: data.tools_allowlist,
      memory_namespace: data.memory_namespace,
      budgets: {
        ...editingAgent.budgets,
        ...data.budgets,
      },
    });
    if (!updated) return false;

    if (currentFlow.created_at) {
      try {
        await updateAgent(currentFlow.id, editingAgent.id, buildAgentPayload({
          ...updated,
          graph: editingAgent.graph,
        }));
      } catch (error) {
        setCurrentFlow(snapshot);
        toast.error(error instanceof Error ? error.message : "Failed to update agent");
        return false;
      }
    }
    toast.success("Agent updated");
    return true;
  }, [buildAgentPayload, currentFlow, editingAgent, setCurrentFlow, storeAddAgent, storeRemoveAgent, updateAgentMeta]);

  const handleDeleteAgent = useCallback(async (agentId: string) => {
    if (!currentFlow) return;
    if (!confirm("Delete this agent and related handoffs/entrypoints?")) return;

    const snapshot = currentFlow;
    const ok = storeRemoveAgent(agentId);
    if (!ok) {
      toast.error("Cannot delete the last agent.");
      return;
    }

    if (currentFlow.created_at) {
      try {
        await deleteAgent(currentFlow.id, agentId);
      } catch (error) {
        setCurrentFlow(snapshot);
        toast.error(error instanceof Error ? error.message : "Failed to delete agent");
        return;
      }
    }
    toast.success("Agent deleted");
  }, [currentFlow, setCurrentFlow, storeRemoveAgent]);

  const openSystemConfig = useCallback((target: SystemConfigTarget) => {
    window.dispatchEvent(new CustomEvent("open-system-config", { detail: target }));
  }, []);

  if (!currentFlow) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ backgroundColor: "var(--bg-primary)" }}>
        <div className="text-center">
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-500/30 flex items-center justify-center">
            <svg className="w-10 h-10 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
          </div>
          <p className="text-[var(--text-secondary)] mb-2 text-lg">No flow loaded</p>
          <p className="text-sm text-[var(--text-muted)]">Create a new flow or load an existing one</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={reactFlowWrapper} className="flex-1 h-full flex flex-col">
      {isV2 && currentFlow?.agents && (
        <AgentSelector
          agents={currentFlow.agents}
          selectedAgentId={selectedAgentId}
          onSelect={setSelectedAgentId}
          onAddAgent={() => {
            setEditingAgent(null);
            setIsAgentModalOpen(true);
          }}
          onEditAgent={(agentId) => {
            const agent = currentFlow.agents?.find((item) => item.id === agentId) || null;
            setEditingAgent(agent);
            setIsAgentModalOpen(true);
          }}
          onDeleteAgent={handleDeleteAgent}
        />
      )}
      {(connectionError || validationIssues.length > 0) && (
        <div className="px-3 py-2 border-b border-amber-700/40 bg-amber-950/30 text-amber-200 text-xs">
          {connectionError && <div>{connectionError}</div>}
          {!connectionError && validationIssues[0] && <div>{validationIssues[0]}</div>}
        </div>
      )}
      <div className="flex-1 relative" style={{ isolation: "isolate" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onNodeContextMenu={onNodeContextMenu}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          onDragOver={onDragOver}
          onDrop={onDrop}
          isValidConnection={(connection) => !validateConnection(connection)}
          nodeTypes={nodeTypes}
          deleteKeyCode={null} // We handle delete ourselves
          fitView
          snapToGrid
          snapGrid={[20, 20]}
          defaultEdgeOptions={{
            type: "smoothstep",
            animated: false,
            markerEnd: {
              type: MarkerType.ArrowClosed,
            },
          }}
          style={{ backgroundColor: "var(--bg-primary)" }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            color="#2a2a2a"
            gap={24}
            size={0.8}
          />
          <Controls
            showInteractive={false}
          />
          <MiniMap
            nodeColor={(node) => {
              const agentId = nodeAgentMap.get(node.id);
              if (agentId) return agentColorMap.get(agentId) || "#64748b";
              return NODE_TYPE_COLORS[node.data?.type as NodeType] || "#64748b";
            }}
            maskColor="rgba(0, 0, 0, 0.7)"
            style={{
              backgroundColor: "var(--bg-tertiary)",
            }}
          />
        </ReactFlow>
        {isV2 && (
          <div className="absolute right-4 top-4 z-20 flex flex-col gap-2 pointer-events-none">
            {SYSTEM_CONFIG_GHOSTS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => openSystemConfig(item.id)}
                className="pointer-events-auto w-52 text-left rounded-xl border px-3 py-2 transition-all hover:translate-y-[-1px]"
                style={{
                  backgroundColor: "rgba(20, 20, 20, 0.88)",
                  borderColor: `${item.color}4D`,
                  boxShadow: "0 10px 24px rgba(0,0,0,0.35)",
                }}
                title={`Open ${item.label}`}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span style={{ color: item.color }}>{item.icon}</span>
                  <span className="text-[11px] font-semibold" style={{ color: item.color }}>
                    {item.label}
                  </span>
                </div>
                <p className="text-[10px] leading-tight text-[var(--text-muted)]">{item.description}</p>
              </button>
            ))}
          </div>
        )}
      </div>
      <AgentConfigModal
        isOpen={isAgentModalOpen}
        isNew={!editingAgent}
        agent={editingAgent}
        onClose={() => setIsAgentModalOpen(false)}
        onSave={async (payload) => {
          const ok = await handleSaveAgent(payload);
          if (ok) {
            setIsAgentModalOpen(false);
          }
        }}
      />
    </div>
  );
}
