"use client";

import { useEffect, useMemo, useState } from "react";
import type { AgentSpec, FallbackSpec, RetrySpec } from "@/types/agents";

interface AdvancedRetryFallbackPanelProps {
  isOpen: boolean;
  onClose: () => void;
  agents: AgentSpec[];
  selectedAgentId: string | null;
  onSave: (agentId: string, retries: RetrySpec, fallbacks: FallbackSpec) => void;
}

export default function AdvancedRetryFallbackPanel({
  isOpen,
  onClose,
  agents,
  selectedAgentId,
  onSave,
}: AdvancedRetryFallbackPanelProps) {
  const [agentId, setAgentId] = useState<string>("");
  const [retries, setRetries] = useState<RetrySpec>({
    max_attempts: 2,
    backoff_ms: 300,
    retry_on: ["timeout", "rate_limit", "5xx"],
    jitter: true,
  });
  const [llmFallbackJson, setLlmFallbackJson] = useState("[]");
  const [toolFallbackJson, setToolFallbackJson] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const currentAgent = useMemo(() => agents.find((a) => a.id === agentId) || null, [agents, agentId]);

  useEffect(() => {
    if (!isOpen) return;
    const first = selectedAgentId || agents[0]?.id || "";
    setAgentId(first);
  }, [isOpen, selectedAgentId, agents]);

  useEffect(() => {
    if (!currentAgent) return;
    setRetries(currentAgent.retries || {
      max_attempts: 2,
      backoff_ms: 300,
      retry_on: ["timeout", "rate_limit", "5xx"],
      jitter: true,
    });
    setLlmFallbackJson(JSON.stringify(currentAgent.fallbacks?.llm_chain || [], null, 2));
    setToolFallbackJson(JSON.stringify(currentAgent.fallbacks?.tool_fallbacks || {}, null, 2));
    setError(null);
  }, [currentAgent]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div
        className="w-full max-w-3xl overflow-hidden rounded-xl border shadow-2xl"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
              Retry & Fallback
            </h2>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              Configure resilience per agent
            </p>
          </div>
          <button onClick={onClose} className="btn-secondary text-xs">Close</button>
        </div>

        <div className="space-y-3 p-4">
        <label className="mb-1 block text-xs" style={{ color: "var(--text-secondary)" }}>
          Agent
          <select value={agentId} onChange={(e) => setAgentId(e.target.value)} className="input-field mt-1 text-xs">
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>{agent.name}</option>
            ))}
          </select>
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Max attempts
            <input type="number" min={1} max={10} value={retries.max_attempts} onChange={(e) => setRetries((r) => ({ ...r, max_attempts: Math.max(1, Number(e.target.value || 1)) }))} className="input-field mt-1 text-xs" />
          </label>
          <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Backoff (ms)
            <input type="number" min={0} max={60000} value={retries.backoff_ms} onChange={(e) => setRetries((r) => ({ ...r, backoff_ms: Math.max(0, Number(e.target.value || 0)) }))} className="input-field mt-1 text-xs" />
          </label>
          <label className="col-span-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            Retry reasons (CSV)
            <input value={retries.retry_on.join(", ")} onChange={(e) => setRetries((r) => ({ ...r, retry_on: e.target.value.split(",").map((v) => v.trim()).filter(Boolean) }))} className="input-field mt-1 text-xs" />
          </label>
          <label className="col-span-2 flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={retries.jitter} onChange={(e) => setRetries((r) => ({ ...r, jitter: e.target.checked }))} />
            Jitter
          </label>
          <label className="col-span-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            LLM fallback chain (JSON array)
            <textarea value={llmFallbackJson} onChange={(e) => setLlmFallbackJson(e.target.value)} rows={5} className="input-field mt-1 min-h-[88px] font-mono text-xs" />
          </label>
          <label className="col-span-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            Tool fallbacks (JSON object: tool {"->"} [fallbacks])
            <textarea value={toolFallbackJson} onChange={(e) => setToolFallbackJson(e.target.value)} rows={5} className="input-field mt-1 min-h-[88px] font-mono text-xs" />
          </label>
        </div>

        {error && <p className="msg-error-soft text-xs">{error}</p>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary text-xs">Cancel</button>
          <button
            onClick={() => {
              try {
                const fallbacks: FallbackSpec = {
                  llm_chain: JSON.parse(llmFallbackJson),
                  tool_fallbacks: JSON.parse(toolFallbackJson),
                };
                if (!agentId) {
                  setError("Select an agent.");
                  return;
                }
                setError(null);
                onSave(agentId, retries, fallbacks);
              } catch {
                setError("Invalid JSON in fallback fields.");
              }
            }}
            className="btn-pill active text-xs"
          >
            Save Retry/Fallback
          </button>
        </div>
        </div>
      </div>
    </div>
  );
}
