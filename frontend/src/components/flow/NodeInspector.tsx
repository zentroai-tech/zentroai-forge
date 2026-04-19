"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFlowStore } from "@/lib/store";
import { NODE_TYPE_LABELS, NODE_TYPE_COLORS, type NodeType, type EnginePreference, type RouterMode, type LLMProvider } from "@/types/ir";
import RouterGuardConfig from "./RouterGuardConfig";
import ModelSelect from "./ModelSelect";
import BrandIcon from "@/components/icons/BrandIcon";
import { listToolContracts } from "@/lib/api";
import type { ToolContractSummary } from "@/types/tools";
import { Divider } from "@/components/ui";

const ENGINE_OPTIONS: { value: EnginePreference | "null"; label: string; icon: "langchain" | "llamaindex" | "auto" | null }[] = [
  { value: "null", label: "Default (inherit)", icon: null },
  { value: "langchain", label: "LangChain", icon: "langchain" },
  { value: "llamaindex", label: "LlamaIndex", icon: "llamaindex" },
  { value: "auto", label: "Auto", icon: "auto" },
];

const PROVIDER_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: "auto", label: "Auto (detect)" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Google Gemini" },
  { value: "anthropic", label: "Anthropic" },
];

function providerToBrand(provider: LLMProvider): "openai" | "gemini" | "claude" | null {
  if (provider === "anthropic") return "claude";
  if (provider === "openai") return "openai";
  if (provider === "gemini") return "gemini";
  return null;
}

type ToolPreset = {
  id: string;
  label: string;
  description: string;
  builder: (mcpServerId: string) => { tool_name: string; tool_config: Record<string, unknown> };
};

// MCP presets are static because they need a serverId and use the mcp: prefix
const MCP_PRESETS: ToolPreset[] = [
  {
    id: "mcp_pubmed",
    label: "MCP PubMed",
    description: "PubMed via MCP tool",
    builder: (serverId) => ({
      tool_name: "mcp:pubmed.search",
      tool_config: {
        mcp_server_id: serverId || "",
        mcp_server: { tool_name: "pubmed.search" },
      },
    }),
  },
  {
    id: "mcp_clinical_trials",
    label: "MCP ClinicalTrials",
    description: "Clinical trials lookup via MCP",
    builder: (serverId) => ({
      tool_name: "mcp:clinical_trials.search",
      tool_config: {
        mcp_server_id: serverId || "",
        mcp_server: { tool_name: "clinical_trials.search" },
      },
    }),
  },
];

// Per-tool default config overrides (tools that need more than an empty config)
const TOOL_CONFIG_DEFAULTS: Record<string, Record<string, unknown>> = {
  qdrant_vector_ops: { provider: "qdrant", default_collection: "default" },
  pinecone_vector_ops: { provider: "pinecone", default_collection: "default" },
};

function contractToLabel(name: string): string {
  return name.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

function contractsToPresets(contracts: ToolContractSummary[]): ToolPreset[] {
  return contracts.map((c) => ({
    id: c.name,
    label: contractToLabel(c.name),
    description: c.description,
    builder: () => ({
      tool_name: c.name,
      tool_config: TOOL_CONFIG_DEFAULTS[c.name] ?? {},
    }),
  }));
}

function getParamsRecord(params: unknown): Record<string, unknown> {
  return (params || {}) as Record<string, unknown>;
}

export default function NodeInspector() {
  const { currentFlow, selectedNodeId, updateNode, removeNode, selectNode, mcpServers } = useFlowStore();
  const selectedNode = currentFlow?.nodes?.find((n) => n.id === selectedNodeId);
  const ownerAgentIdFromNodeId =
    selectedNode?.id && selectedNode.id.includes("::")
      ? selectedNode.id.split("::")[0]
      : null;

  // Find which agent owns this node (v2 flows only)
  const ownerAgent = ownerAgentIdFromNodeId
    ? currentFlow?.agents?.find((agent) => agent.id === ownerAgentIdFromNodeId)
    : undefined;
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [selectedToolPreset, setSelectedToolPreset] = useState<string>("");
  const [isEngineMenuOpen, setIsEngineMenuOpen] = useState(false);
  const engineMenuRef = useRef<HTMLDivElement>(null);
  const [toolContracts, setToolContracts] = useState<ToolContractSummary[]>([]);

  // Fetch tool contracts from the registry API so presets stay in sync with the backend
  useEffect(() => {
    listToolContracts()
      .then(setToolContracts)
      .catch(() => {
        // Non-fatal: presets will only show MCP entries until backend is reachable
      });
  }, []);

  // Merge API-driven presets (all registered contracts) with static MCP presets
  const allPresets = useMemo<ToolPreset[]>(
    () => [...contractsToPresets(toolContracts), ...MCP_PRESETS],
    [toolContracts]
  );

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (engineMenuRef.current && !engineMenuRef.current.contains(event.target as Node)) {
        setIsEngineMenuOpen(false);
      }
    };
    if (isEngineMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isEngineMenuOpen]);

  const handleNameChange = useCallback(
    (value: string) => {
      if (selectedNodeId) updateNode(selectedNodeId, { name: value });
    },
    [selectedNodeId, updateNode]
  );

  const handleParamChange = useCallback(
    (key: string, value: unknown) => {
      if (!selectedNode) return;
      const newParams = { ...selectedNode.params, [key]: value };
      updateNode(selectedNode.id, { params: newParams });
    },
    [selectedNode, updateNode]
  );

  const handleDelete = useCallback(() => {
    if (selectedNodeId && confirm("Delete this node?")) removeNode(selectedNodeId);
  }, [selectedNodeId, removeNode]);

  if (!selectedNode) {
    return (
      <div className="w-80 panel flex flex-col h-full border-l border-[var(--border-default)]">
        <div className="h-10 px-3 flex items-center border-b border-[var(--border-default)]">
          <h2 className="text-[11px] font-semibold text-[var(--text-secondary)]">Inspector</h2>
        </div>
        <div className="flex-1 flex items-center justify-center p-4">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-default)] flex items-center justify-center">
              <svg className="w-6 h-6 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
              </svg>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">Select a node to edit</p>
            <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Click on any node in the canvas</p>
          </div>
        </div>
      </div>
    );
  }

  const accentColor = NODE_TYPE_COLORS[selectedNode.type as NodeType];
  const params = getParamsRecord(selectedNode.params);
  const isStartNode = Boolean(params.is_start);
  const toolConfigRecord = (params.tool_config as Record<string, unknown> | undefined) || {};
  const mcpConfig = (toolConfigRecord.mcp_server as Record<string, unknown> | undefined) || {};
  const isMcpTool = Boolean(
    (params.tool_name as string | undefined)?.startsWith("mcp:") || toolConfigRecord.mcp_server
  );

  const selectedMcpServerId = (toolConfigRecord.mcp_server_id as string | undefined) || "";
  const selectedMcpServer = mcpServers.find((server) => server.id === selectedMcpServerId);

  const applyMcpServer = (serverId: string) => {
    const server = mcpServers.find((s) => s.id === serverId);
    if (!server) return;
    const currentToolName = (params.tool_name as string | undefined) || "";
    const rawToolName =
      (mcpConfig.tool_name as string | undefined) ||
      (currentToolName.startsWith("mcp:") ? currentToolName.slice(4) : "");
    const mergedConfig = {
      ...toolConfigRecord,
      mcp_server_id: server.id,
      mcp_server: {
        ...(mcpConfig || {}),
        command: server.command,
        args: server.args,
        cwd: server.cwd || undefined,
        env: server.env || {},
        timeout_seconds: server.timeout_seconds ?? 20,
        tool_name: rawToolName || undefined,
      },
    };
    handleParamChange("tool_config", mergedConfig);
  };

  const renderParamsEditor = () => {
    switch (selectedNode.type) {
      case "LLM":
        return (
          <>
            <Field label="Provider">
              <div className="grid grid-cols-2 gap-2">
                {PROVIDER_OPTIONS.map((opt) => {
                  const selected = ((params.provider as string) || "auto") === opt.value;
                  const brand = providerToBrand(opt.value);
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => handleParamChange("provider", opt.value)}
                      className={`h-8 px-2 text-[10px] flex items-center gap-2 chip-option ${selected ? "active" : ""}`}
                    >
                      {brand ? (
                        <BrandIcon name={brand} size={14} alt={opt.label} tone={selected ? "bright" : "muted"} />
                      ) : (
                        <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">A</span>
                      )}
                      <span className="truncate">{opt.label}</span>
                    </button>
                  );
                })}
              </div>
            </Field>
            <Field label="Model">
              <ModelSelect
                provider={(params.provider as LLMProvider) || "auto"}
                value={(params.model as string) || "gpt-3.5-turbo"}
                projectId={currentFlow?.id || "default"}
                onChange={(modelId) => handleParamChange("model", modelId)}
              />
            </Field>
            <Field label="System Prompt">
              <textarea
                value={(params.system_prompt as string) || ""}
                onChange={(e) => handleParamChange("system_prompt", e.target.value || null)}
                className="input-field min-h-[60px] resize-y"
                placeholder="You are a helpful assistant..."
              />
            </Field>
            <Field label="Prompt Template">
              <textarea
                value={(params.prompt_template as string) || "{input}"}
                onChange={(e) => handleParamChange("prompt_template", e.target.value)}
                className="input-field min-h-[48px] resize-y"
                placeholder="{input}"
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Temperature">
                <input
                  type="number" min={0} max={2} step={0.1}
                  value={(params.temperature as number) ?? 0.7}
                  onChange={(e) => handleParamChange("temperature", parseFloat(e.target.value))}
                  className="input-field"
                />
              </Field>
              <Field label="Max Tokens">
                <input
                  type="number" min={1}
                  value={(params.max_tokens as number) || ""}
                  onChange={(e) => handleParamChange("max_tokens", e.target.value ? parseInt(e.target.value) : null)}
                  className="input-field"
                  placeholder="Default"
                />
              </Field>
            </div>
            <Divider label="Resilience" />
            <div className="grid grid-cols-3 gap-2">
              <Field label="Retries">
                <input type="number" min={0} max={10}
                  value={(params.retry_count as number) ?? 0}
                  onChange={(e) => handleParamChange("retry_count", parseInt(e.target.value) || 0)}
                  className="input-field"
                />
              </Field>
              <Field label="Delay (s)">
                <input type="number" min={0} step={0.5}
                  value={(params.retry_delay as number) ?? 1.0}
                  onChange={(e) => handleParamChange("retry_delay", parseFloat(e.target.value) || 1.0)}
                  className="input-field"
                />
              </Field>
              <Field label="Timeout">
                <input type="number" min={0}
                  value={(params.timeout_seconds as number) || ""}
                  onChange={(e) => handleParamChange("timeout_seconds", e.target.value ? parseFloat(e.target.value) : null)}
                  className="input-field"
                  placeholder="None"
                />
              </Field>
            </div>
          </>
        );

      case "Tool":
        return (
          <>
            <Field label="Quick Presets">
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <select
                  value={selectedToolPreset}
                  onChange={(e) => setSelectedToolPreset(e.target.value)}
                  className="input-field"
                >
                  <option value="">Choose preset...</option>
                  {allPresets.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.label}
                    </option>
                  ))}
                </select>
                <button
                  className="btn-secondary px-2 text-[10px]"
                  onClick={() => {
                    if (!selectedToolPreset) return;
                    const preset = allPresets.find((p) => p.id === selectedToolPreset);
                    if (!preset) return;
                    const next = preset.builder(selectedMcpServerId);
                    handleParamChange("tool_name", next.tool_name);
                    handleParamChange("tool_config", {
                      ...(toolConfigRecord || {}),
                      ...(next.tool_config || {}),
                    });
                  }}
                >
                  Apply
                </button>
              </div>
              {selectedToolPreset && (
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                  {allPresets.find((p) => p.id === selectedToolPreset)?.description}
                </p>
              )}
            </Field>
            <Field label="Tool Name">
              <input type="text"
                value={(params.tool_name as string) || ""}
                onChange={(e) => handleParamChange("tool_name", e.target.value)}
                className="input-field"
                placeholder="e.g., web_search"
              />
            </Field>
            <Field label="Tool Config (JSON)">
              <textarea
                value={JSON.stringify(params.tool_config || {}, null, 2)}
                onChange={(e) => {
                  try { handleParamChange("tool_config", JSON.parse(e.target.value)); setJsonError(null); }
                  catch { setJsonError("Invalid JSON"); }
                }}
                className="input-field min-h-[80px] font-mono text-[10px] resize-y"
                placeholder='{}'
              />
              {jsonError && <p className="text-[10px] mt-1 msg-error-soft">{jsonError}</p>}
            </Field>
            <Field label="MCP">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isMcpTool}
                  onChange={(e) => {
                    if (e.target.checked) {
                      const fallbackTool = (params.tool_name as string) || "mcp:tool_name";
                      const nextToolName = fallbackTool.startsWith("mcp:") ? fallbackTool : `mcp:${fallbackTool}`;
                      handleParamChange("tool_name", nextToolName);
                      const nextConfig = {
                        ...toolConfigRecord,
                        mcp_server: {
                          ...(mcpConfig || {}),
                          command: typeof mcpConfig.command === "string" ? mcpConfig.command : "",
                          args: Array.isArray(mcpConfig.args) ? mcpConfig.args : [],
                          cwd: typeof mcpConfig.cwd === "string" ? mcpConfig.cwd : undefined,
                          env: typeof mcpConfig.env === "object" ? mcpConfig.env : {},
                          timeout_seconds: typeof mcpConfig.timeout_seconds === "number" ? mcpConfig.timeout_seconds : 20,
                        },
                      };
                      handleParamChange("tool_config", nextConfig);
                    } else {
                      const nextToolName = (params.tool_name as string)?.startsWith("mcp:")
                        ? ""
                        : params.tool_name;
                      const nextConfig = { ...toolConfigRecord };
                      delete nextConfig.mcp_server;
                      delete nextConfig.mcp_server_id;
                      handleParamChange("tool_name", nextToolName);
                      handleParamChange("tool_config", nextConfig);
                    }
                  }}
                />
                <span className="text-[10px] text-[var(--text-secondary)]">Use MCP server</span>
              </label>
            </Field>
            {isMcpTool && (
              <>
                <Field label="MCP Server">
                  <select
                    value={selectedMcpServerId}
                    onChange={(e) => applyMcpServer(e.target.value)}
                    className="input-field"
                  >
                    <option value="">Select server</option>
                    {mcpServers.map((server) => (
                      <option key={server.id} value={server.id}>
                        {server.name} ({server.id})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="MCP Tool Name">
                  <input
                    type="text"
                    value={
                      (mcpConfig.tool_name as string | undefined) ||
                      (((params.tool_name as string) || "").startsWith("mcp:")
                        ? ((params.tool_name as string).slice(4))
                        : "")
                    }
                    onChange={(e) => {
                      const tool = e.target.value.trim();
                      const nextConfig = {
                        ...toolConfigRecord,
                        mcp_server_id: selectedMcpServerId || toolConfigRecord.mcp_server_id,
                        mcp_server: {
                          ...(mcpConfig || {}),
                          tool_name: tool,
                        },
                      };
                      handleParamChange("tool_name", tool ? `mcp:${tool}` : "mcp:");
                      handleParamChange("tool_config", nextConfig);
                    }}
                    className="input-field"
                    placeholder="e.g. pubmed.search"
                  />
                </Field>
                {!selectedMcpServer && (
                  <p className="text-[10px] msg-warning-soft">
                    Configure/select a server in Toolbar {'>'} MCP.
                  </p>
                )}
              </>
            )}
            <Divider label="Resilience" />
            <div className="grid grid-cols-3 gap-2">
              <Field label="Retries">
                <input type="number" min={0} max={10} value={(params.retry_count as number) ?? 0}
                  onChange={(e) => handleParamChange("retry_count", parseInt(e.target.value) || 0)} className="input-field" />
              </Field>
              <Field label="Delay (s)">
                <input type="number" min={0} step={0.5} value={(params.retry_delay as number) ?? 1.0}
                  onChange={(e) => handleParamChange("retry_delay", parseFloat(e.target.value) || 1.0)} className="input-field" />
              </Field>
              <Field label="Timeout">
                <input type="number" min={0} value={(params.timeout_seconds as number) || ""}
                  onChange={(e) => handleParamChange("timeout_seconds", e.target.value ? parseFloat(e.target.value) : null)}
                  className="input-field" placeholder="None" />
              </Field>
            </div>
          </>
        );

      case "Error":
        return (
          <Field label="Error Template">
            <textarea
              value={(params.error_template as string) || "An error occurred while processing this request."}
              onChange={(e) => handleParamChange("error_template", e.target.value)}
              className="input-field min-h-[60px] resize-y"
              placeholder="Fallback error message..."
            />
          </Field>
        );

      case "Parallel":
        return (
          <Field label="Mode">
            <select
              value={(params.mode as string) || "broadcast"}
              onChange={(e) => handleParamChange("mode", e.target.value)}
              className="input-field"
            >
              <option value="broadcast">broadcast</option>
            </select>
          </Field>
        );

      case "Join":
        return (
          <Field label="Join Strategy">
            <select
              value={(params.strategy as string) || "array"}
              onChange={(e) => handleParamChange("strategy", e.target.value)}
              className="input-field"
            >
              <option value="array">array</option>
              <option value="dict">dict</option>
              <option value="last_non_null">last_non_null</option>
            </select>
          </Field>
        );

      case "Retriever":
        return (
          <>
            <Field label="Query Template">
              <textarea value={(params.query_template as string) || "{input}"}
                onChange={(e) => handleParamChange("query_template", e.target.value)}
                className="input-field min-h-[48px] resize-y" placeholder="{input}" />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Top K">
                <input type="number" min={1} max={100} value={(params.top_k as number) ?? 5}
                  onChange={(e) => handleParamChange("top_k", parseInt(e.target.value))} className="input-field" />
              </Field>
              <Field label="Index Name">
                <input type="text" value={(params.index_name as string) || ""}
                  onChange={(e) => handleParamChange("index_name", e.target.value || null)}
                  className="input-field" placeholder="my-index" />
              </Field>
            </div>
            <Field label="Index Config (JSON)">
              <textarea value={JSON.stringify(params.index_config || {}, null, 2)}
                onChange={(e) => {
                  try { handleParamChange("index_config", JSON.parse(e.target.value)); setJsonError(null); }
                  catch { setJsonError("Invalid JSON"); }
                }}
                className="input-field min-h-[60px] font-mono text-[10px] resize-y" placeholder='{}' />
              {jsonError && <p className="text-[10px] mt-1 msg-error-soft">{jsonError}</p>}
            </Field>
          </>
        );

      case "Memory":
        return (
          <>
            <Field label="Memory Type">
              <select value={(params.memory_type as string) || "buffer"}
                onChange={(e) => handleParamChange("memory_type", e.target.value)}
                className="input-field">
                <option value="buffer">Buffer</option>
                <option value="summary">Summary</option>
                <option value="vector">Vector</option>
              </select>
            </Field>
            <Field label="Max Tokens">
              <input type="number" min={100} value={(params.max_tokens as number) ?? 2000}
                onChange={(e) => handleParamChange("max_tokens", parseInt(e.target.value))}
                className="input-field" />
            </Field>
          </>
        );

      case "Router": {
        const outgoingEdges = currentFlow?.edges?.filter(e => e.source === selectedNode.id) || [];
        const nodeTargets = currentFlow?.nodes?.map(n => ({ id: n.id, name: n.name })) || [];
        return (
          <>
            <RouterGuardConfig
              mode={(params.mode as RouterMode) || "llm"}
              minDocs={(params.min_docs as number) ?? 1}
              minTopScore={(params.min_top_score as number) ?? 0.65}
              groundedBranch={(params.grounded_branch as string) || null}
              abstainBranch={(params.abstain_branch as string) || null}
              outgoingEdges={outgoingEdges}
              nodeTargets={nodeTargets}
              onModeChange={(mode) => handleParamChange("mode", mode)}
              onMinDocsChange={(value) => handleParamChange("min_docs", value)}
              onMinTopScoreChange={(value) => handleParamChange("min_top_score", value)}
              onGroundedBranchChange={(nodeId) => handleParamChange("grounded_branch", nodeId)}
              onAbstainBranchChange={(nodeId) => handleParamChange("abstain_branch", nodeId)}
            />
            {(params.mode as RouterMode) === "llm" && (
              <>
                <Field label="Routes (JSON)">
                  <textarea value={JSON.stringify(params.routes || {}, null, 2)}
                    onChange={(e) => {
                      try { handleParamChange("routes", JSON.parse(e.target.value)); setJsonError(null); }
                      catch { setJsonError("Invalid JSON"); }
                    }}
                    className="input-field min-h-[80px] font-mono text-[10px] resize-y"
                    placeholder='{"condition": "target_node_id"}' />
                  {jsonError && <p className="text-[10px] mt-1 msg-error-soft">{jsonError}</p>}
                </Field>
                <Field label="Default Route">
                  <input type="text" value={(params.default_route as string) || ""}
                    onChange={(e) => handleParamChange("default_route", e.target.value || null)}
                    className="input-field" placeholder="Node ID" />
                </Field>
              </>
            )}
          </>
        );
      }

      case "Output":
        return (
          <>
            <Field label="Output Template">
              <textarea value={(params.output_template as string) || "{result}"}
                onChange={(e) => handleParamChange("output_template", e.target.value)}
                className="input-field min-h-[48px] resize-y" placeholder="{result}" />
            </Field>
            <Field label="Format">
              <select value={(params.format as string) || "text"}
                onChange={(e) => handleParamChange("format", e.target.value)}
                className="input-field">
                <option value="text">Text</option>
                <option value="json">JSON</option>
                <option value="markdown">Markdown</option>
              </select>
            </Field>
          </>
        );

      default:
        return <p className="text-[10px] text-[var(--text-muted)]">No parameters</p>;
    }
  };

  return (
    <div className="w-80 panel flex flex-col h-full overflow-hidden border-l border-[var(--border-default)]">
      {/* ── Header ──────────────────────────── */}
      <div className="h-10 px-4 border-b border-[var(--border-default)] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: accentColor }}
          />
          <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: accentColor }}>
            {NODE_TYPE_LABELS[selectedNode.type as NodeType]}
          </span>
        </div>
        <button
          onClick={() => selectNode(null)}
          className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* ── Agent assignment (v2 only) ──────── */}
      {ownerAgent && (
        <div className="px-4 py-1.5 border-b border-[var(--border-default)] flex items-center gap-1.5">
          <span className="text-[9px] text-[var(--text-muted)]">Agent:</span>
          <span className="text-[10px] font-medium text-violet-400">{ownerAgent.name}</span>
          <span className="text-[9px] text-[var(--text-muted)]">({ownerAgent.llm.model})</span>
        </div>
      )}

      {/* ── Scrollable content ──────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        <Field label="Node Name">
          <input type="text" value={selectedNode.name}
            onChange={(e) => handleNameChange(e.target.value)}
            className="input-field" />
        </Field>

        <Field label="Start Node">
          <label className="flex items-center gap-2 cursor-pointer">
            <div className="relative">
              <input type="checkbox" checked={isStartNode}
                onChange={(e) => handleParamChange("is_start", e.target.checked)}
                className="sr-only"
              />
              <div
                className="w-8 h-4 rounded-full transition-colors border border-[var(--border-default)]"
                style={{
                  backgroundColor: isStartNode ? "var(--border-active)" : "var(--bg-tertiary)",
                }}
              />
              <div
                className="absolute left-0.5 top-0.5 w-3 h-3 bg-white rounded-full transition-transform"
                style={{
                  transform: isStartNode ? "translateX(16px)" : "translateX(0px)",
                }}
              />
            </div>
            <span className="text-[10px] text-[var(--text-secondary)]">Entry point</span>
          </label>
        </Field>

        <Divider label="Parameters" />
        {renderParamsEditor()}

        {selectedNode.type !== "Output" && (
          <>
            <Divider label="Engine Override" />
            <Field label="Engine">
              <div className="relative" ref={engineMenuRef}>
                {(() => {
                  const currentValue = params.engine === null || params.engine === undefined
                    ? "null"
                    : (params.engine as string);
                  const selectedOption = ENGINE_OPTIONS.find((opt) => opt.value === currentValue) || ENGINE_OPTIONS[0];
                  return (
                    <>
                      <button
                        type="button"
                        onClick={() => setIsEngineMenuOpen((prev) => !prev)}
                        className="input-field h-9 flex items-center justify-between"
                        style={isEngineMenuOpen ? { backgroundColor: "var(--bg-selected)", borderColor: "var(--border-active)" } : undefined}
                      >
                        <span className="flex items-center gap-2">
                          {selectedOption.icon === "langchain" && (
                            <BrandIcon name="langchain" size={14} alt="LangChain" tone="bright" />
                          )}
                          {selectedOption.icon === "llamaindex" && (
                            <BrandIcon name="llamaindex" size={14} alt="LlamaIndex" tone="bright" />
                          )}
                          {selectedOption.icon === "auto" && (
                            <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">
                              A
                            </span>
                          )}
                          {selectedOption.icon === null && (
                            <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">
                              D
                            </span>
                          )}
                          <span>{selectedOption.label}</span>
                        </span>
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                      {isEngineMenuOpen && (
                        <div
                          className="absolute left-0 right-0 top-full mt-1 rounded-md border z-50 overflow-hidden"
                          style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
                        >
                          {ENGINE_OPTIONS.map((opt) => (
                            <button
                              key={opt.value}
                              type="button"
                              className="w-full h-9 px-3 text-xs flex items-center gap-2 hover:bg-[var(--bg-tertiary)]"
                              style={{
                                backgroundColor: currentValue === opt.value ? "var(--bg-selected)" : "transparent",
                                color: currentValue === opt.value ? "var(--text-primary)" : "var(--text-secondary)",
                              }}
                              onClick={() => {
                                handleParamChange("engine", opt.value === "null" ? null : opt.value);
                                setIsEngineMenuOpen(false);
                              }}
                            >
                              {opt.icon === "langchain" && <BrandIcon name="langchain" size={14} alt="LangChain" tone="bright" />}
                              {opt.icon === "llamaindex" && <BrandIcon name="llamaindex" size={14} alt="LlamaIndex" tone="bright" />}
                              {opt.icon === "auto" && (
                                <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">
                                  A
                                </span>
                              )}
                              {opt.icon === null && (
                                <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">
                                  D
                                </span>
                              )}
                              <span>{opt.label}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            </Field>
          </>
        )}

        <div className="pt-2">
          <button onClick={handleDelete} className="w-full btn-danger">
            <span className="flex items-center justify-center gap-1.5">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete Node
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] font-medium text-[var(--text-secondary)] mb-1.5">{label}</label>
      {children}
    </div>
  );
}

