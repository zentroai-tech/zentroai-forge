"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import type { EvalRun, EvalCaseResult, EvalCase } from "@/types/eval";
import { downloadReport } from "@/lib/evalsApi";

/* ------------------------------------------------------------------ */
/*  Props                                                             */
/* ------------------------------------------------------------------ */

interface EvalRunResultsProps {
  run: EvalRun;
  results: EvalCaseResult[];
  /** All cases in the suite — used to resolve case_id → name */
  cases: EvalCase[];
  onViewRun: (runId: string) => void;
}

/* ------------------------------------------------------------------ */
/*  Main component                                                    */
/* ------------------------------------------------------------------ */

export default function EvalRunResults({ run, results, cases, onViewRun }: EvalRunResultsProps) {
  const passRate =
    run.total_cases > 0
      ? Math.round((run.passed_cases / run.total_cases) * 100)
      : 0;

  const caseMap = new Map(cases.map((c) => [c.id, c]));

  const handleDownload = async () => {
    try {
      const blob = await downloadReport(run.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `eval_report_${run.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to download report");
    }
  };

  return (
    <div className="space-y-6">
      {/* Summary card */}
      <div
        className="rounded-xl p-6 border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">
            Run Results
          </h3>
          <div className="flex items-center gap-3">
            {run.gate_passed !== null && run.gate_passed !== undefined && (
              <span
                className={`px-2 py-0.5 text-xs rounded-full font-medium ${
                  run.gate_passed
                    ? "bg-green-500/20 text-green-400"
                    : "bg-red-500/20 text-red-400"
                }`}
              >
                Gate: {run.gate_passed ? "PASS" : "FAIL"}
              </span>
            )}
            <StatusBadge status={run.status} />
            <span className="text-xs text-[var(--text-muted)]">
              {new Date(run.created_at).toLocaleString()}
            </span>
            {run.status === "completed" && (
              <button
                type="button"
                onClick={handleDownload}
                className="text-xs text-[var(--text-secondary)] hover:text-white flex items-center gap-1"
                title="Download JSON report"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Report
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div
              className={`text-3xl font-bold ${
                passRate >= 80
                  ? "text-green-400"
                  : passRate >= 50
                    ? "text-amber-400"
                    : "text-red-400"
              }`}
            >
              {passRate}%
            </div>
            <div className="text-xs text-[var(--text-muted)] mt-1">Pass Rate</div>
          </div>

          <div className="text-center">
            <div className="text-3xl font-bold text-green-400">{run.passed_cases}</div>
            <div className="text-xs text-[var(--text-muted)] mt-1">Passed</div>
          </div>

          <div className="text-center">
            <div className="text-3xl font-bold text-red-400">{run.failed_cases}</div>
            <div className="text-xs text-[var(--text-muted)] mt-1">Failed</div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-4 h-2 rounded-full overflow-hidden bg-[var(--bg-primary)]">
          <div
            className="h-full bg-green-500 transition-all"
            style={{ width: `${passRate}%` }}
          />
        </div>

        {/* Timing info */}
        {run.started_at && run.finished_at && (
          <p className="text-xs text-[var(--text-muted)] mt-3">
            Duration: {Math.round(
              (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime())
            )}ms
          </p>
        )}
      </div>

      {/* Results table */}
      {results.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
            Case Results
          </h4>
          <div className="space-y-2">
            {results.map((result) => (
              <CaseResultRow
                key={result.id}
                result={result}
                caseName={caseMap.get(result.case_id)?.name ?? result.case_id}
                onViewRun={onViewRun}
              />
            ))}
          </div>
        </div>
      )}

      {results.length === 0 && run.status !== "completed" && (
        <div className="text-center py-8 text-[var(--text-muted)]">
          <p className="text-sm">
            {run.status === "running" ? "Run is in progress…" : "No results available yet."}
          </p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CaseResultRow                                                     */
/* ------------------------------------------------------------------ */

function CaseResultRow({
  result,
  caseName,
  onViewRun,
}: {
  result: EvalCaseResult;
  caseName: string;
  onViewRun: (runId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const passed = result.status === "passed";
  const failed = result.status === "failed";

  return (
    <div
      className="rounded-xl border transition-all"
      style={{
        backgroundColor: passed
          ? "rgba(34, 197, 94, 0.05)"
          : failed
            ? "rgba(239, 68, 68, 0.05)"
            : "var(--bg-secondary)",
        borderColor: passed
          ? "rgba(34, 197, 94, 0.2)"
          : failed
            ? "rgba(239, 68, 68, 0.2)"
            : "var(--border-default)",
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-6 h-6 rounded-full flex items-center justify-center ${
              passed ? "bg-green-500/20" : failed ? "bg-red-500/20" : "bg-amber-500/20"
            }`}
          >
            {passed ? (
              <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : failed ? (
              <svg className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
          </div>
          <div>
            <span className="text-sm font-medium text-white">{caseName}</span>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`text-xs ${passed ? "text-green-400" : failed ? "text-red-400" : "text-amber-400"}`}>
                {result.status}
              </span>
              {result.duration_ms != null && (
                <span className="text-xs text-[var(--text-muted)]">
                  {Math.round(result.duration_ms)}ms
                </span>
              )}
            </div>
            {result.error_message && (
              <p className="text-xs text-red-400 mt-0.5 line-clamp-1">{result.error_message}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {result.run_id && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onViewRun(result.run_id!);
              }}
              className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] underline"
            >
              View Run
            </button>
          )}
          <svg
            className={`w-4 h-4 text-[var(--text-muted)] transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-[var(--border-default)]">
          <div className="space-y-2">
            {result.error_message && (
              <div className="p-2 rounded-md bg-red-500/10 text-sm text-red-400">
                {result.error_message}
              </div>
            )}

            {result.assertions && result.assertions.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">
                  Assertion Results
                </label>
                {result.assertions.map((assertion, i) => {
                  const assertionPassed =
                    (assertion as Record<string, unknown>).passed === true ||
                    (assertion as Record<string, unknown>).status === "passed";

                  return (
                    <div
                      key={i}
                      className={`flex items-center gap-2 px-2 py-1 rounded text-xs ${
                        assertionPassed
                          ? "bg-green-500/10 text-green-400"
                          : "bg-red-500/10 text-red-400"
                      }`}
                    >
                      {assertionPassed ? (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      )}
                      <span className="font-mono">
                        {(assertion as Record<string, unknown>).type as string ??
                          (assertion as Record<string, unknown>).assertion as string ??
                          JSON.stringify(assertion)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {result.duration_ms != null && (
              <p className="text-xs text-[var(--text-muted)]">
                Duration: {Math.round(result.duration_ms)}ms
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  StatusBadge                                                       */
/* ------------------------------------------------------------------ */

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string }> = {
    pending: { bg: "bg-amber-500/20", text: "text-amber-400" },
    running: { bg: "bg-blue-500/20", text: "text-blue-400" },
    completed: { bg: "bg-green-500/20", text: "text-green-400" },
    failed: { bg: "bg-red-500/20", text: "text-red-400" },
  };
  const s = map[status] ?? map.pending;
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full ${s.bg} ${s.text}`}>
      {status}
    </span>
  );
}
