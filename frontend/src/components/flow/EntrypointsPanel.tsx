"use client";

import { useMemo, useState } from "react";
import type { AgentSpec, EntrypointSpec } from "@/types/agents";

interface EntrypointsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  agents: AgentSpec[];
  entrypoints: EntrypointSpec[];
  onChange: (entrypoints: EntrypointSpec[]) => void;
}

export default function EntrypointsPanel({
  isOpen,
  onClose,
  agents,
  entrypoints,
  onChange,
}: EntrypointsPanelProps) {
  const [newName, setNewName] = useState("");
  const [newAgentId, setNewAgentId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const agentOptions = useMemo(() => agents.map((a) => ({ id: a.id, name: a.name })), [agents]);
  if (!isOpen) return null;

  const handleAdd = () => {
    const name = newName.trim();
    if (!name || !newAgentId) {
      setError("Entrypoint name and target agent are required.");
      return;
    }
    if (entrypoints.some((entry) => entry.name === name)) {
      setError("Entrypoint names must be unique.");
      return;
    }
    setError(null);
    onChange([...entrypoints, { name, agent_id: newAgentId, description: "" }]);
    setNewName("");
    setNewAgentId("");
  };

  const handleRemove = (name: string) => {
    if (entrypoints.length <= 1) {
      setError("At least one entrypoint is required.");
      return;
    }
    const updated = entrypoints.filter((entry) => entry.name !== name);
    if (!updated.some((entry) => entry.name === "main") && updated.length > 0) {
      updated[0] = { ...updated[0], name: "main" };
    }
    onChange(updated);
  };

  const handleAgentChange = (name: string, agentId: string) => {
    onChange(
      entrypoints.map((entry) =>
        entry.name === name ? { ...entry, agent_id: agentId } : entry
      )
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div
        className="w-full max-w-2xl overflow-hidden rounded-xl border shadow-2xl"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
              Entrypoints
            </h2>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              Define start routes for run execution
            </p>
          </div>
          <button onClick={onClose} className="btn-secondary text-xs">
            Close
          </button>
        </div>

        <div className="space-y-3 p-4">
          <div
            className="rounded-lg border p-3"
            style={{ backgroundColor: "var(--bg-tertiary)", borderColor: "var(--border-default)" }}
          >
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              New Entrypoint
            </div>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="entrypoint name"
                className="input-field text-xs"
              />
              <select
                value={newAgentId}
                onChange={(e) => setNewAgentId(e.target.value)}
                className="input-field text-xs"
              >
                <option value="">target agent</option>
                {agentOptions.map((agent) => (
                  <option key={agent.id} value={agent.id}>{agent.name}</option>
                ))}
              </select>
              <button onClick={handleAdd} className="btn-pill text-xs active">
                Add Entrypoint
              </button>
            </div>
          </div>
          {error && <p className="msg-error-soft text-xs">{error}</p>}

          <div className="max-h-[360px] space-y-2 overflow-auto rounded-lg border p-2" style={{ borderColor: "var(--border-default)" }}>
            {entrypoints.map((entry) => (
              <div key={entry.name} className="grid grid-cols-1 items-center gap-2 rounded-md border p-2 md:grid-cols-4" style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}>
                <div className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>{entry.name}</div>
                <select
                  value={entry.agent_id}
                  onChange={(e) => handleAgentChange(entry.name, e.target.value)}
                  className="input-field md:col-span-2 text-xs"
                >
                  {agentOptions.map((agent) => (
                    <option key={`${entry.name}-${agent.id}`} value={agent.id}>{agent.name}</option>
                  ))}
                </select>
                <button
                  onClick={() => handleRemove(entry.name)}
                  className="btn-secondary text-xs"
                  style={{ color: "#fca5a5" }}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
