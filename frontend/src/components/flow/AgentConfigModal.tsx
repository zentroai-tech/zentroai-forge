"use client";

import { useEffect, useState } from "react";
import type { AgentSpec, BudgetSpec, LlmBinding } from "@/types/agents";
import BrandIcon from "@/components/icons/BrandIcon";
import { Button } from "@/components/ui";

interface AgentConfigModalProps {
  agent?: AgentSpec | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: {
    id: string;
    name: string;
    llm: Partial<LlmBinding>;
    tools_allowlist: string[];
    memory_namespace: string | null;
    budgets: Partial<BudgetSpec>;
  }) => void;
  isNew?: boolean;
}

export default function AgentConfigModal({
  agent,
  isOpen,
  onClose,
  onSave,
  isNew = false,
}: AgentConfigModalProps) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [provider, setProvider] = useState("auto");
  const [temperature, setTemperature] = useState(0.7);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [toolsAllowlist, setToolsAllowlist] = useState("");
  const [memoryNamespace, setMemoryNamespace] = useState("");
  const [maxTokens, setMaxTokens] = useState<string>("");
  const [maxSteps, setMaxSteps] = useState<string>("");
  const [maxToolCalls, setMaxToolCalls] = useState<string>("");
  const [maxDepth, setMaxDepth] = useState(5);
  const [error, setError] = useState<string | null>(null);

  const providerOptions: Array<{ value: string; label: string; brand: "openai" | "gemini" | "claude" | null }> = [
    { value: "auto", label: "Auto", brand: null },
    { value: "openai", label: "OpenAI", brand: "openai" },
    { value: "gemini", label: "Gemini", brand: "gemini" },
    { value: "anthropic", label: "Anthropic", brand: "claude" },
  ];

  useEffect(() => {
    if (!isOpen) return;
    setId(agent?.id ?? "");
    setName(agent?.name ?? "");
    setModel(agent?.llm.model ?? "gpt-4o-mini");
    setProvider(agent?.llm.provider ?? "auto");
    setTemperature(agent?.llm.temperature ?? 0.7);
    setSystemPrompt(agent?.llm.system_prompt ?? "");
    setToolsAllowlist(agent?.tools_allowlist.join(", ") ?? "");
    setMemoryNamespace(agent?.memory_namespace ?? "");
    setMaxTokens(agent?.budgets.max_tokens?.toString() ?? "");
    setMaxSteps(agent?.budgets.max_steps?.toString() ?? "");
    setMaxToolCalls(agent?.budgets.max_tool_calls?.toString() ?? "");
    setMaxDepth(agent?.budgets.max_depth ?? 5);
    setError(null);
  }, [isOpen, agent, isNew]);

  if (!isOpen) return null;

  const handleSave = () => {
    const normalizedId = id.toLowerCase().replace(/[^a-z0-9_]/g, "_");
    if (!normalizedId.match(/^[a-z][a-z0-9_]*$/)) {
      setError("Agent ID must start with a letter and contain only a-z, 0-9, _");
      return;
    }
    if (!name.trim()) {
      setError("Agent name is required");
      return;
    }

    onSave({
      id: normalizedId,
      name: name.trim(),
      llm: {
        provider,
        model,
        temperature,
        system_prompt: systemPrompt || null,
      },
      tools_allowlist: toolsAllowlist
        ? toolsAllowlist.split(",").map((s) => s.trim()).filter(Boolean)
        : [],
      memory_namespace: memoryNamespace || null,
      budgets: {
        max_tokens: maxTokens ? parseInt(maxTokens) : null,
        max_steps: maxSteps ? parseInt(maxSteps) : null,
        max_tool_calls: maxToolCalls ? parseInt(maxToolCalls) : null,
        max_depth: maxDepth,
      },
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-xl w-full max-w-lg max-h-[85vh] overflow-y-auto p-6">
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
          {isNew ? "New Agent" : `Edit Agent: ${agent?.name}`}
        </h2>
        {error && (
          <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* ID & Name */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                Agent ID
              </label>
              <input
                value={id}
                onChange={(e) => setId(e.target.value)}
                disabled={!isNew}
                placeholder="e.g. researcher"
                className="w-full px-3 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)] disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Research Agent"
                className="w-full px-3 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
              />
            </div>
          </div>

          {/* LLM Config */}
          <div>
            <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">
              LLM Configuration
            </h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  Provider
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {providerOptions.map((opt) => {
                    const selected = provider === opt.value;
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setProvider(opt.value)}
                        className={`h-8 px-2 text-[11px] flex items-center gap-2 chip-option ${selected ? "active" : ""}`}
                      >
                        {opt.brand ? (
                          <BrandIcon name={opt.brand} size={14} alt={opt.label} tone={selected ? "bright" : "muted"} />
                        ) : (
                          <span className="inline-flex w-3.5 h-3.5 items-center justify-center text-[9px] font-semibold rounded-full border border-[var(--border-default)]">A</span>
                        )}
                        <span className="truncate">{opt.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  Model
                </label>
                <input
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full px-2 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
                />
              </div>
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  Temperature
                </label>
                <input
                  type="number"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  min={0}
                  max={2}
                  step={0.1}
                  className="w-full px-2 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
                />
              </div>
            </div>
          </div>

          {/* System Prompt */}
          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              System Prompt
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={3}
              placeholder="Optional system prompt for this agent..."
              className="w-full px-3 py-2 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)] resize-none"
            />
          </div>

          {/* Tool Allowlist */}
          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              Tool Allowlist (comma-separated, empty = all)
            </label>
            <input
              value={toolsAllowlist}
              onChange={(e) => setToolsAllowlist(e.target.value)}
              placeholder="web_search, calculator"
              className="w-full px-3 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
            />
          </div>

          {/* Memory Namespace */}
          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              Memory Namespace
            </label>
            <input
              value={memoryNamespace}
              onChange={(e) => setMemoryNamespace(e.target.value)}
              placeholder="Optional shared namespace"
              className="w-full px-3 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
            />
          </div>

          {/* Budgets */}
          <div>
            <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">Budgets</h3>
            <div className="grid grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  Max Tokens
                </label>
                <input
                  type="number"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(e.target.value)}
                  placeholder="None"
                  className="w-full px-2 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
                />
              </div>
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  Max Steps
                </label>
                <input
                  type="number"
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(e.target.value)}
                  placeholder="None"
                  className="w-full px-2 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
                />
              </div>
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  Max Tool Calls
                </label>
                <input
                  type="number"
                  value={maxToolCalls}
                  onChange={(e) => setMaxToolCalls(e.target.value)}
                  placeholder="None"
                  className="w-full px-2 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
                />
              </div>
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  Max Depth
                </label>
                <input
                  type="number"
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(parseInt(e.target.value))}
                  min={1}
                  max={20}
                  className="w-full px-2 py-1.5 text-sm bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-md text-[var(--text-primary)]"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={!id || !name}>
            {isNew ? "Create Agent" : "Save Changes"}
          </Button>
        </div>
      </div>
    </div>
  );
}
