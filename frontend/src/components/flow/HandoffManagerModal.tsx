"use client";

import { useMemo, useState } from "react";
import type { AgentSpec, HandoffMode, HandoffRule } from "@/types/agents";
import HandoffTable from "./HandoffTable";

interface HandoffManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  agents: AgentSpec[];
  handoffs: HandoffRule[];
  onAdd: (handoff: HandoffRule) => void;
  onRemove: (index: number) => void;
}

export default function HandoffManagerModal({
  isOpen,
  onClose,
  agents,
  handoffs,
  onAdd,
  onRemove,
}: HandoffManagerModalProps) {
  const [fromAgentId, setFromAgentId] = useState("");
  const [toAgentId, setToAgentId] = useState("");
  const [mode, setMode] = useState<HandoffMode>("call");
  const [error, setError] = useState<string | null>(null);

  const canCreate = useMemo(() => agents.length >= 2, [agents.length]);

  if (!isOpen) return null;

  const handleAdd = () => {
    if (!fromAgentId || !toAgentId) {
      setError("Select source and target agents.");
      return;
    }
    if (fromAgentId === toAgentId) {
      setError("A handoff cannot target the same agent.");
      return;
    }
    const exists = handoffs.some(
      (h) => h.from_agent_id === fromAgentId && h.to_agent_id === toAgentId && h.mode === mode
    );
    if (exists) {
      setError("This handoff already exists.");
      return;
    }
    setError(null);
    onAdd({
      from_agent_id: fromAgentId,
      to_agent_id: toAgentId,
      mode,
      guard: null,
      input_schema: null,
      output_schema: null,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div
        className="w-full max-w-3xl overflow-hidden rounded-xl border shadow-2xl"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
              Handoff Manager
            </h2>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              Route control between agents
            </p>
          </div>
          <button onClick={onClose} className="btn-secondary text-xs">Close</button>
        </div>

        <div className="space-y-3 p-4">
        <div className="rounded-lg border p-3" style={{ backgroundColor: "var(--bg-tertiary)", borderColor: "var(--border-default)" }}>
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            New Handoff
          </div>
          {!canCreate ? (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>Create at least 2 agents to define handoffs.</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
              <select
                value={fromAgentId}
                onChange={(e) => setFromAgentId(e.target.value)}
                className="input-field text-xs"
              >
                <option value="">From agent</option>
                {agents.map((agent) => (
                  <option key={`from-${agent.id}`} value={agent.id}>{agent.name}</option>
                ))}
              </select>
              <select
                value={toAgentId}
                onChange={(e) => setToAgentId(e.target.value)}
                className="input-field text-xs"
              >
                <option value="">To agent</option>
                {agents.map((agent) => (
                  <option key={`to-${agent.id}`} value={agent.id}>{agent.name}</option>
                ))}
              </select>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as HandoffMode)}
                className="input-field text-xs"
              >
                <option value="call">call</option>
                <option value="delegate">delegate</option>
              </select>
              <button onClick={handleAdd} className="btn-pill text-xs active">Add Handoff</button>
            </div>
          )}
          {error && <p className="mt-2 msg-error-soft text-xs">{error}</p>}
        </div>

        <div className="max-h-[360px] overflow-auto rounded-lg border p-1" style={{ borderColor: "var(--border-default)" }}>
          <HandoffTable
            handoffs={handoffs}
            agents={agents}
            onAdd={() => {}}
            onRemove={onRemove}
          />
        </div>
        </div>
      </div>
    </div>
  );
}
