"use client";

import { useCallback } from "react";
import type { RouterMode, FlowEdge } from "@/types/ir";

interface RouterGuardConfigProps {
  mode: RouterMode;
  minDocs: number;
  minTopScore: number;
  groundedBranch: string | null;
  abstainBranch: string | null;
  outgoingEdges: FlowEdge[];
  nodeTargets: { id: string; name: string }[];
  onModeChange: (mode: RouterMode) => void;
  onMinDocsChange: (value: number) => void;
  onMinTopScoreChange: (value: number) => void;
  onGroundedBranchChange: (nodeId: string | null) => void;
  onAbstainBranchChange: (nodeId: string | null) => void;
}

export default function RouterGuardConfig({
  mode,
  minDocs,
  minTopScore,
  groundedBranch,
  abstainBranch,
  outgoingEdges,
  nodeTargets,
  onModeChange,
  onMinDocsChange,
  onMinTopScoreChange,
  onGroundedBranchChange,
  onAbstainBranchChange,
}: RouterGuardConfigProps) {
  // Get available targets from outgoing edges
  const availableTargets = outgoingEdges
    .map((edge) => {
      const target = nodeTargets.find((n) => n.id === edge.target);
      return target ? { id: edge.target, name: target.name } : null;
    })
    .filter(Boolean) as { id: string; name: string }[];

  return (
    <div className="space-y-4">
      {/* Mode Selector */}
      <div>
        <label className="block text-xs font-medium text-[var(--text-secondary)] mb-2">
          Router Mode
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => onModeChange("llm")}
            className={`flex-1 px-3 py-2 text-sm rounded-lg border-2 transition-all ${
              mode === "llm"
                ? "border-[var(--border-active)] bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                : "border-[var(--border-default)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]"
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              LLM Routing
            </div>
          </button>
          <button
            onClick={() => onModeChange("guard")}
            className={`flex-1 px-3 py-2 text-sm rounded-lg border-2 transition-all ${
              mode === "guard"
                ? "border-green-500 bg-green-500/10 text-green-400"
                : "border-[var(--border-default)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]"
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Guard (RAG)
            </div>
          </button>
        </div>
      </div>

      {/* Guard Mode Configuration */}
      {mode === "guard" && (
        <div className="space-y-4 p-3 rounded-lg bg-green-500/5 border border-green-500/20">
          <div className="flex items-center gap-2 text-xs text-green-400 mb-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            RAG Grounding Guard Configuration
          </div>

          {/* Min Docs */}
          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
              Minimum Documents Required
            </label>
            <input
              type="number"
              min={0}
              max={20}
              value={minDocs}
              onChange={(e) => onMinDocsChange(parseInt(e.target.value) || 0)}
              className="input-field w-full"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              Minimum number of retrieved docs to consider grounded
            </p>
          </div>

          {/* Min Top Score */}
          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
              Minimum Top Score
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minTopScore}
                onChange={(e) => onMinTopScoreChange(parseFloat(e.target.value))}
                className="flex-1 accent-green-500"
              />
              <span className="text-sm font-mono text-[var(--text-secondary)] w-12 text-right">
                {minTopScore.toFixed(2)}
              </span>
            </div>
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              Minimum similarity score threshold for grounding
            </p>
          </div>

          {/* Branch Targets */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-green-400 mb-1.5">
                Grounded Branch
              </label>
              <select
                value={groundedBranch || ""}
                onChange={(e) => onGroundedBranchChange(e.target.value || null)}
                className="input-field w-full text-sm"
              >
                <option value="">Select target...</option>
                {availableTargets.map((target) => (
                  <option key={target.id} value={target.id}>
                    {target.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-amber-400 mb-1.5">
                Abstain Branch
              </label>
              <select
                value={abstainBranch || ""}
                onChange={(e) => onAbstainBranchChange(e.target.value || null)}
                className="input-field w-full text-sm"
              >
                <option value="">Select target...</option>
                {availableTargets.map((target) => (
                  <option key={target.id} value={target.id}>
                    {target.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {availableTargets.length === 0 && (
            <div className="text-xs text-amber-400 bg-amber-500/10 p-2 rounded">
              Connect outgoing edges to other nodes to configure branches
            </div>
          )}
        </div>
      )}
    </div>
  );
}
