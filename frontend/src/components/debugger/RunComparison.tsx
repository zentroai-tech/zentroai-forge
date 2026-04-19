"use client";

import { useState, useEffect } from "react";
import { getRunComparison } from "@/lib/api";

interface RunComparisonProps {
  runId: string;
  originalRunId: string;
}

interface ComparisonData {
  output_diff: { added: string[]; removed: string[] };
  decision_diff: { field: string; original: unknown; replay: unknown }[];
  score_diff: { original: number; replay: number };
}

export default function RunComparison({ runId, originalRunId }: RunComparisonProps) {
  const [comparison, setComparison] = useState<ComparisonData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadComparison() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await getRunComparison(runId, originalRunId);
        setComparison(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load comparison");
      } finally {
        setIsLoading(false);
      }
    }
    loadComparison();
  }, [runId, originalRunId]);

  if (isLoading) {
    return (
      <div className="p-4 rounded-xl bg-[var(--bg-secondary)]">
        <div className="flex items-center gap-2 text-[var(--text-muted)]">
          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading comparison...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20">
        <div className="flex items-center gap-2 text-red-400 text-sm">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {error}
        </div>
      </div>
    );
  }

  if (!comparison) return null;

  const hasOutputChanges = comparison.output_diff.added.length > 0 || comparison.output_diff.removed.length > 0;
  const hasDecisionChanges = comparison.decision_diff.length > 0;
  const scoreChanged = comparison.score_diff.original !== comparison.score_diff.replay;

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-default)",
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 border-b flex items-center gap-2"
        style={{ borderColor: "var(--border-default)" }}
      >
        <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <span className="text-sm font-medium text-white">Compared to Run</span>
        <code className="text-xs font-mono text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded">
          {originalRunId.slice(0, 8)}...
        </code>
      </div>

      <div className="p-4 space-y-4">
        {/* Score Diff */}
        {scoreChanged && (
          <div>
            <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">Top Score</div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)]">Original:</span>
                <span className="text-sm font-mono text-white">
                  {comparison.score_diff.original.toFixed(3)}
                </span>
              </div>
              <svg className="w-4 h-4 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)]">Replay:</span>
                <span
                  className={`text-sm font-mono ${
                    comparison.score_diff.replay > comparison.score_diff.original
                      ? "text-green-400"
                      : comparison.score_diff.replay < comparison.score_diff.original
                      ? "text-red-400"
                      : "text-white"
                  }`}
                >
                  {comparison.score_diff.replay.toFixed(3)}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Decision Diff */}
        {hasDecisionChanges && (
          <div>
            <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">Decision Changes</div>
            <div className="space-y-2">
              {comparison.decision_diff.map((diff, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 p-2 rounded-lg bg-[var(--bg-tertiary)] text-sm"
                >
                  <span className="text-[var(--text-muted)] font-mono">{diff.field}</span>
                  <span className="text-red-400 line-through">{String(diff.original)}</span>
                  <svg className="w-3 h-3 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                  <span className="text-green-400">{String(diff.replay)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Output Diff */}
        {hasOutputChanges && (
          <div>
            <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">Output Changes</div>
            <div className="space-y-1 font-mono text-xs">
              {comparison.output_diff.removed.map((line, i) => (
                <div key={`r-${i}`} className="flex">
                  <span className="text-red-400 w-4">-</span>
                  <span className="text-red-400/80">{line}</span>
                </div>
              ))}
              {comparison.output_diff.added.map((line, i) => (
                <div key={`a-${i}`} className="flex">
                  <span className="text-green-400 w-4">+</span>
                  <span className="text-green-400/80">{line}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {!hasOutputChanges && !hasDecisionChanges && !scoreChanged && (
          <div className="text-sm text-[var(--text-muted)] text-center py-2">
            No differences detected
          </div>
        )}
      </div>
    </div>
  );
}
