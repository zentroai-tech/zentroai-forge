"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import { diffRuns, type RunDiffResult, type RunNodeDiff } from "@/lib/api";
import type { RunListItem } from "@/types/ir";

interface RunDiffProps {
  runs: RunListItem[];
}

function formatDelta(value: number, unit: string, invert = false): { text: string; cls: string } {
  if (value === 0) return { text: `±0 ${unit}`, cls: "text-[var(--text-muted)]" };
  const better = invert ? value < 0 : value > 0;
  const sign = value > 0 ? "+" : "";
  return {
    text: `${sign}${Math.round(value)} ${unit}`,
    cls: better ? "text-green-400" : "text-red-400",
  };
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "completed"
      ? "bg-green-900/40 text-green-300"
      : status === "failed"
      ? "bg-red-900/40 text-red-300"
      : status === "missing"
      ? "bg-zinc-800 text-zinc-500"
      : "bg-yellow-900/40 text-yellow-300";
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${cls}`}>{status}</span>
  );
}

function NodeDiffRow({ diff, expanded, onToggle }: { diff: RunNodeDiff; expanded: boolean; onToggle: () => void }) {
  const hasDiff = diff.output_changed || diff.status_a !== diff.status_b || diff.token_delta !== 0;
  const tokenDelta = formatDelta(diff.token_delta, "tok", false);
  const durDelta = formatDelta(diff.duration_delta_ms, "ms", true);

  return (
    <div
      className={`border-b last:border-b-0 transition-colors ${hasDiff ? "border-amber-900/30" : ""}`}
      style={{ borderColor: hasDiff ? undefined : "var(--border-default)" }}
    >
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-[var(--bg-tertiary)] transition-colors"
      >
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: hasDiff ? "#f59e0b" : "#22c55e" }}
        />
        <span className="text-xs font-mono text-white flex-1 truncate">{diff.node_id}</span>
        <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0">{diff.node_type}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusBadge status={diff.status_a} />
          <span className="text-[var(--text-muted)]">→</span>
          <StatusBadge status={diff.status_b} />
        </div>
        <span className={`text-[10px] flex-shrink-0 ${tokenDelta.cls}`}>{tokenDelta.text}</span>
        <span className={`text-[10px] flex-shrink-0 ${durDelta.cls}`}>{durDelta.text}</span>
        <svg
          className={`w-3.5 h-3.5 flex-shrink-0 transition-transform text-[var(--text-muted)] ${expanded ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div
          className="px-4 pb-3 space-y-3 border-t"
          style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}
        >
          {/* Model change */}
          {diff.model_a !== diff.model_b && (diff.model_a || diff.model_b) && (
            <div className="pt-2">
              <p className="text-[10px] text-[var(--text-muted)] mb-1">Model</p>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-red-400 line-through font-mono">{diff.model_a || "—"}</span>
                <span className="text-[var(--text-muted)]">→</span>
                <span className="text-green-400 font-mono">{diff.model_b || "—"}</span>
              </div>
            </div>
          )}

          {/* Output diff */}
          {diff.output_changed && (
            <div className="pt-2">
              <p className="text-[10px] text-[var(--text-muted)] mb-1">Output diff</p>
              <div
                className="font-mono text-xs rounded p-2 space-y-0.5 max-h-48 overflow-y-auto"
                style={{ backgroundColor: "var(--bg-secondary)" }}
              >
                {diff.output_diff.removed.map((line, i) => (
                  <div key={`r-${i}`} className="flex gap-2">
                    <span className="text-red-400 select-none">-</span>
                    <span className="text-red-400/80 break-all">{line}</span>
                  </div>
                ))}
                {diff.output_diff.added.map((line, i) => (
                  <div key={`a-${i}`} className="flex gap-2">
                    <span className="text-green-400 select-none">+</span>
                    <span className="text-green-400/80 break-all">{line}</span>
                  </div>
                ))}
                {diff.output_diff.removed.length === 0 && diff.output_diff.added.length === 0 && (
                  <span className="text-[var(--text-muted)]">(outputs differ but no line-level changes)</span>
                )}
              </div>
            </div>
          )}

          {!diff.output_changed && diff.status_a === diff.status_b && diff.token_delta === 0 && (
            <p className="text-xs text-[var(--text-muted)] pt-2">No differences</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function RunDiff({ runs }: RunDiffProps) {
  const [runAId, setRunAId] = useState<string>("");
  const [runBId, setRunBId] = useState<string>("");
  const [result, setResult] = useState<RunDiffResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  const handleDiff = async () => {
    if (!runAId || !runBId) {
      toast.error("Select both runs to compare");
      return;
    }
    if (runAId === runBId) {
      toast.error("Select two different runs");
      return;
    }
    setIsLoading(true);
    setExpandedNodes(new Set());
    try {
      const data = await diffRuns(runAId, runBId);
      setResult(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Diff failed");
    } finally {
      setIsLoading(false);
    }
  };

  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const selectProps = {
    className: "rounded-lg px-2.5 py-1.5 text-xs flex-1 min-w-0",
    style: {
      backgroundColor: "var(--bg-tertiary)",
      border: "1px solid var(--border-default)",
      color: "var(--text-secondary)",
    },
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Selectors */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b flex-shrink-0"
        style={{ borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xs text-red-400 font-medium flex-shrink-0">A</span>
          <select value={runAId} onChange={(e) => { setRunAId(e.target.value); setResult(null); }} {...selectProps}>
            <option value="">Select run A (baseline)</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id.slice(0, 20)}… · {r.status} · {r.created_at?.slice(0, 16)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xs text-green-400 font-medium flex-shrink-0">B</span>
          <select value={runBId} onChange={(e) => { setRunBId(e.target.value); setResult(null); }} {...selectProps}>
            <option value="">Select run B (comparison)</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id.slice(0, 20)}… · {r.status} · {r.created_at?.slice(0, 16)}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={handleDiff}
          disabled={isLoading || !runAId || !runBId}
          className="btn-pill text-xs flex-shrink-0 px-4"
        >
          {isLoading ? "Diffing…" : "Diff"}
        </button>
      </div>

      {/* Result */}
      <div className="flex-1 overflow-y-auto">
        {!result && !isLoading && (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Select two runs and click Diff
            </p>
          </div>
        )}

        {isLoading && (
          <div className="flex items-center justify-center h-full gap-2" style={{ color: "var(--text-muted)" }}>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Computing diff…
          </div>
        )}

        {result && (
          <div className="p-4 space-y-4">
            {/* Summary cards */}
            <div className="grid grid-cols-2 gap-3">
              {/* Run A */}
              <div
                className="rounded-lg border p-3 space-y-1"
                style={{ borderColor: "rgba(248,113,113,0.3)", backgroundColor: "rgba(248,113,113,0.05)" }}
              >
                <p className="text-[10px] font-medium text-red-400 uppercase tracking-wider">Run A (baseline)</p>
                <p className="text-xs font-mono text-white truncate">{result.run_a.id}</p>
                <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
                  <span>{result.run_a.status}</span>
                  <span>{result.run_a.total_tokens} tok</span>
                  {result.run_a.duration_ms != null && <span>{Math.round(result.run_a.duration_ms)}ms</span>}
                </div>
              </div>
              {/* Run B */}
              <div
                className="rounded-lg border p-3 space-y-1"
                style={{ borderColor: "rgba(74,222,128,0.3)", backgroundColor: "rgba(74,222,128,0.05)" }}
              >
                <p className="text-[10px] font-medium text-green-400 uppercase tracking-wider">Run B (comparison)</p>
                <p className="text-xs font-mono text-white truncate">{result.run_b.id}</p>
                <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
                  <span>{result.run_b.status}</span>
                  <span>{result.run_b.total_tokens} tok</span>
                  {result.run_b.duration_ms != null && <span>{Math.round(result.run_b.duration_ms)}ms</span>}
                </div>
              </div>
            </div>

            {/* Stats bar */}
            <div
              className="rounded-lg border px-4 py-2.5 flex items-center flex-wrap gap-4 text-xs"
              style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
            >
              <div>
                <span style={{ color: "var(--text-muted)" }}>Changed nodes: </span>
                <span className={result.summary.changed_nodes > 0 ? "text-amber-400" : "text-green-400"}>
                  {result.summary.changed_nodes}/{result.summary.total_nodes}
                </span>
              </div>
              <div>
                {(() => {
                  const d = formatDelta(result.summary.token_delta, "tok", false);
                  return (
                    <>
                      <span style={{ color: "var(--text-muted)" }}>Tokens: </span>
                      <span className={d.cls}>{d.text}</span>
                    </>
                  );
                })()}
              </div>
              <div>
                {(() => {
                  const d = formatDelta(result.summary.duration_delta_ms, "ms", true);
                  return (
                    <>
                      <span style={{ color: "var(--text-muted)" }}>Duration: </span>
                      <span className={d.cls}>{d.text}</span>
                    </>
                  );
                })()}
              </div>
              {(result.summary.tool_failure_rate_a > 0 || result.summary.tool_failure_rate_b > 0) && (
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Tool failures: </span>
                  <span className="text-[var(--text-secondary)]">
                    {(result.summary.tool_failure_rate_a * 100).toFixed(0)}%
                    {" → "}
                    {(result.summary.tool_failure_rate_b * 100).toFixed(0)}%
                  </span>
                </div>
              )}
            </div>

            {/* Node diffs table */}
            <div
              className="rounded-lg border overflow-hidden"
              style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
            >
              <div
                className="px-4 py-2 border-b grid text-[10px] font-medium uppercase tracking-wider"
                style={{
                  borderColor: "var(--border-default)",
                  color: "var(--text-muted)",
                  gridTemplateColumns: "1rem 1fr 5rem 8rem 5rem 5rem 1.5rem",
                  gap: "0.75rem",
                }}
              >
                <span />
                <span>Node</span>
                <span>Type</span>
                <span>Status A → B</span>
                <span>Tokens Δ</span>
                <span>Duration Δ</span>
                <span />
              </div>
              {result.node_diffs.length === 0 ? (
                <p className="text-xs text-center py-4" style={{ color: "var(--text-muted)" }}>
                  No nodes to compare
                </p>
              ) : (
                result.node_diffs.map((diff) => (
                  <NodeDiffRow
                    key={diff.node_id}
                    diff={diff}
                    expanded={expandedNodes.has(diff.node_id)}
                    onToggle={() => toggleNode(diff.node_id)}
                  />
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
