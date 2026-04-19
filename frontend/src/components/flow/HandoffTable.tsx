"use client";

import type { HandoffRule, AgentSpec } from "@/types/agents";
import { Button } from "@/components/ui";

interface HandoffTableProps {
  handoffs: HandoffRule[];
  agents: AgentSpec[];
  onAdd?: () => void;
  onRemove: (index: number) => void;
}

export default function HandoffTable({
  handoffs,
  agents,
  onAdd,
  onRemove,
}: HandoffTableProps) {
  const getAgentName = (id: string) =>
    agents.find((a) => a.id === id)?.name ?? id;

  if (handoffs.length === 0) {
    return (
      <div className="p-4 text-center text-[var(--text-muted)] text-sm">
        <p>No handoff rules defined.</p>
        {onAdd && (
          <Button variant="primary" size="sm" onClick={onAdd} className="mt-2">
            Add Handoff
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-700/50 text-zinc-400 text-xs">
            <th className="text-left px-3 py-2">From</th>
            <th className="text-left px-3 py-2"></th>
            <th className="text-left px-3 py-2">To</th>
            <th className="text-left px-3 py-2">Mode</th>
            <th className="text-right px-3 py-2">
              {onAdd && (
                <Button variant="ghost" size="sm" onClick={onAdd}>
                  + Add
                </Button>
              )}
            </th>
          </tr>
        </thead>
        <tbody>
          {handoffs.map((h, idx) => (
            <tr
              key={idx}
              className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
            >
              <td className="px-3 py-2 text-zinc-200">
                {getAgentName(h.from_agent_id)}
              </td>
              <td className="px-1 py-2 text-zinc-500 text-center">&rarr;</td>
              <td className="px-3 py-2 text-zinc-200">
                {getAgentName(h.to_agent_id)}
              </td>
              <td className="px-3 py-2">
                <span
                  className={`px-2 py-0.5 rounded text-xs ${
                    h.mode === "call"
                      ? "bg-emerald-900/40 text-emerald-400"
                      : "bg-amber-900/40 text-amber-400"
                  }`}
                >
                  {h.mode}
                </span>
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  onClick={() => onRemove(idx)}
                  className="text-zinc-500 hover:text-red-400 text-xs"
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
