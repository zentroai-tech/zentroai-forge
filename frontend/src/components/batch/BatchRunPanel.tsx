"use client";

import { useState, useCallback } from "react";
import toast from "react-hot-toast";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface BatchResult {
  index: number;
  run_id: string;
  status: string;
  output?: string | null;
  error?: string | null;
  duration_ms?: number | null;
  tokens_total?: number | null;
}

interface BatchRunPanelProps {
  flowId: string;
  onClose: () => void;
  embedded?: boolean;
}

export default function BatchRunPanel({ flowId, onClose, embedded }: BatchRunPanelProps) {
  const [rawInput, setRawInput] = useState('{"input": "Hello"}\n{"input": "What can you do?"}');
  const [results, setResults] = useState<BatchResult[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [summary, setSummary] = useState<{
    total: number;
    completed: number;
    failed: number;
  } | null>(null);

  const handleRun = useCallback(async () => {
    const lines = rawInput.split("\n").filter((l) => l.trim());
    const inputs: Record<string, unknown>[] = [];
    for (let i = 0; i < lines.length; i++) {
      try {
        inputs.push(JSON.parse(lines[i]));
      } catch {
        toast.error(`Invalid JSON on line ${i + 1}`);
        return;
      }
    }

    if (inputs.length === 0) {
      toast.error("Add at least one input (one JSON per line)");
      return;
    }

    setIsRunning(true);
    setResults([]);
    setSummary(null);

    try {
      const res = await fetch(`${API_BASE}/flows/${flowId}/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Batch run failed");
      }

      const data = await res.json();
      setResults(data.results);
      setSummary({
        total: data.total,
        completed: data.completed,
        failed: data.failed,
      });
      toast.success(`Batch complete: ${data.completed}/${data.total} passed`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Batch run failed");
    } finally {
      setIsRunning(false);
    }
  }, [rawInput, flowId]);

  const handleExportCSV = useCallback(() => {
    if (results.length === 0) return;
    const header = "index,status,output,tokens,duration_ms,error\n";
    const rows = results.map((r) => {
      const output = (r.output || "").replace(/"/g, '""');
      const error = (r.error || "").replace(/"/g, '""');
      return `${r.index},${r.status},"${output}",${r.tokens_total || ""},${r.duration_ms || ""},"${error}"`;
    });
    const csv = header + rows.join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `batch_results_${flowId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [results, flowId]);

  const contentBody = (
    <div className="flex-1 flex overflow-hidden">
          <div className="w-1/2 flex flex-col border-r" style={{ borderColor: "var(--border-default)" }}>
            <div className="p-3 border-b flex items-center justify-between" style={{ borderColor: "var(--border-default)" }}>
              <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                Inputs (JSONLines — one JSON object per line)
              </span>
              <button
                onClick={handleRun}
                disabled={isRunning}
                className="btn-pill"
                style={{
                  opacity: isRunning ? 0.5 : 1,
                }}
              >
                {isRunning ? "Running..." : `Run ${rawInput.split("\n").filter((l) => l.trim()).length} inputs`}
              </button>
            </div>
            <textarea
              value={rawInput}
              onChange={(e) => setRawInput(e.target.value)}
              disabled={isRunning}
              className="flex-1 p-3 font-mono text-xs resize-none focus:outline-none"
              style={{
                backgroundColor: "var(--bg-primary)",
                color: "var(--text-primary)",
                border: "none",
              }}
              placeholder='{"input": "Hello"}\n{"input": "What is RAG?"}'
            />
          </div>

          <div className="w-1/2 flex flex-col">
            <div className="p-3 border-b flex items-center justify-between" style={{ borderColor: "var(--border-default)" }}>
              <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                Results
                {summary && (
                  <span className="ml-2" style={{ color: "var(--text-muted)" }}>
                    ({summary.completed}/{summary.total} passed)
                  </span>
                )}
              </span>
              {results.length > 0 && (
                <button
                  onClick={handleExportCSV}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-[var(--bg-tertiary)]"
                  style={{ color: "var(--text-muted)", border: "1px solid var(--border-default)" }}
                >
                  Export CSV
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-2" style={{ backgroundColor: "var(--bg-primary)" }}>
              {results.length === 0 && !isRunning && (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    Results will appear here after running
                  </p>
                </div>
              )}
              {isRunning && results.length === 0 && (
                <div className="flex items-center justify-center h-full">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-[var(--text-muted)] animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="w-2 h-2 rounded-full bg-[var(--text-muted)] animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="w-2 h-2 rounded-full bg-[var(--text-muted)] animate-bounce" style={{ animationDelay: "300ms" }} />
                    <span className="text-sm" style={{ color: "var(--text-muted)" }}>Running batch...</span>
                  </div>
                </div>
              )}
              {results.map((r) => (
                <div
                  key={r.index}
                  className="rounded-lg p-3 border text-xs"
                  style={{
                    backgroundColor: "var(--bg-secondary)",
                    borderColor: r.status === "completed" ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)",
                  }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                      #{r.index + 1}
                    </span>
                    <div className="flex items-center gap-2">
                      {r.tokens_total && (
                        <span style={{ color: "var(--text-muted)" }}>{r.tokens_total.toLocaleString()} tok</span>
                      )}
                      {r.duration_ms && (
                        <span style={{ color: "var(--text-muted)" }}>{(r.duration_ms / 1000).toFixed(1)}s</span>
                      )}
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{
                          backgroundColor: r.status === "completed" ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                          color: r.status === "completed" ? "#22c55e" : "#ef4444",
                        }}
                      >
                        {r.status}
                      </span>
                    </div>
                  </div>
                  {r.output && (
                    <div
                      className="mt-1 whitespace-pre-wrap break-words"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {r.output.length > 300 ? r.output.slice(0, 300) + "..." : r.output}
                    </div>
                  )}
                  {r.error && (
                    <div className="mt-1 text-red-400">{r.error}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
  );

  if (embedded) return <div className="h-full flex flex-col">{contentBody}</div>;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-4xl mx-4 h-[85vh] flex flex-col border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        <div
          className="p-4 border-b flex items-center justify-between flex-shrink-0"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Batch Run</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-muted)" }}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {contentBody}
      </div>
    </div>
  );
}
