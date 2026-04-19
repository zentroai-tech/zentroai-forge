"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import toast from "react-hot-toast";
import type { EvalSuite, EvalCase, EvalRun, EvalCaseResult } from "@/types/eval";
import * as api from "@/lib/evalsApi";
import EvalSuiteEditor from "./EvalSuiteEditor";
import EvalRunResults from "./EvalRunResults";
import DatasetUploadModal from "./DatasetUploadModal";
import ThresholdsModal from "./ThresholdsModal";

/* ------------------------------------------------------------------ */
/*  Props                                                             */
/* ------------------------------------------------------------------ */

interface FlowEvalsPageProps {
  flowId: string;
  onViewRun: (runId: string) => void;
  onClose: () => void;
  embedded?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Tiny loading spinner                                               */
/* ------------------------------------------------------------------ */

function Spinner({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                    */
/* ------------------------------------------------------------------ */

export default function FlowEvalsPage({ flowId, onViewRun, onClose, embedded }: FlowEvalsPageProps) {
  /* ---- abort on unmount ---- */
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    abortRef.current = new AbortController();
    return () => { abortRef.current?.abort(); };
  }, []);
  const signal = () => abortRef.current?.signal;

  /* ---- state ---- */
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [selectedSuiteId, setSelectedSuiteId] = useState<string | null>(null);
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [selectedRunResults, setSelectedRunResults] = useState<{
    run: EvalRun;
    results: EvalCaseResult[];
  } | null>(null);

  const [isLoadingSuites, setIsLoadingSuites] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newSuiteName, setNewSuiteName] = useState("");
  const [showDatasetUpload, setShowDatasetUpload] = useState(false);
  const [showThresholds, setShowThresholds] = useState(false);

  /* ---- derived ---- */
  const selectedSuite = suites.find((s) => s.id === selectedSuiteId) ?? null;

  /* ---------------------------------------------------------------- */
  /*  Fetch helpers                                                   */
  /* ---------------------------------------------------------------- */

  const loadSuites = useCallback(async () => {
    if (!flowId) return;
    setIsLoadingSuites(true);
    try {
      const data = await api.listSuites(flowId, 50, 0, signal());
      setSuites(data);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      toast.error(err instanceof Error ? err.message : "Failed to load eval suites");
    } finally {
      setIsLoadingSuites(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowId]);

  const loadSuiteDetail = useCallback(async (suiteId: string) => {
    setIsLoadingDetail(true);
    setSelectedRunResults(null);
    try {
      const [caseList, runList] = await Promise.all([
        api.listCases(suiteId, signal()),
        api.listRuns(suiteId, 20, signal()),
      ]);
      setCases(caseList);
      setRuns(runList);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      toast.error(err instanceof Error ? err.message : "Failed to load suite details");
    } finally {
      setIsLoadingDetail(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* initial load */
  useEffect(() => { loadSuites(); }, [loadSuites]);

  /* reload detail when selectedSuiteId changes */
  useEffect(() => {
    if (selectedSuiteId) loadSuiteDetail(selectedSuiteId);
    else { setCases([]); setRuns([]); setSelectedRunResults(null); }
  }, [selectedSuiteId, loadSuiteDetail]);

  /* ---------------------------------------------------------------- */
  /*  Handlers                                                        */
  /* ---------------------------------------------------------------- */

  const handleSelectSuite = (suiteId: string) => {
    setSelectedSuiteId(suiteId);
  };

  const handleCreateSuite = async () => {
    const name = newSuiteName.trim();
    if (!name) { toast.error("Please enter a suite name"); return; }

    setIsLoadingSuites(true);
    try {
      const suite = await api.createSuite(flowId, { name }, signal());
      setSuites((prev) => [...prev, suite]);
      setSelectedSuiteId(suite.id);
      setNewSuiteName("");
      setIsCreating(false);
      toast.success("Eval suite created");
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      toast.error(err instanceof Error ? err.message : "Failed to create suite");
    } finally {
      setIsLoadingSuites(false);
    }
  };

  const handleDeleteSuite = async (suiteId: string) => {
    if (!confirm("Delete this eval suite and all its cases?")) return;

    try {
      await api.deleteSuite(suiteId, signal());
      setSuites((prev) => prev.filter((s) => s.id !== suiteId));
      if (selectedSuiteId === suiteId) {
        setSelectedSuiteId(null);
      }
      toast.success("Suite deleted");
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      toast.error(err instanceof Error ? err.message : "Failed to delete suite");
    }
  };

  const handleRunSuite = async () => {
    if (!selectedSuiteId) return;

    setIsRunning(true);
    try {
      const run = await api.runSuite(selectedSuiteId, undefined, signal());
      toast.success("Run started");

      // Reload runs list
      const updatedRuns = await api.listRuns(selectedSuiteId, 20, signal());
      setRuns(updatedRuns);

      // Immediately try to load results (run may already be completed)
      try {
        const results = await api.getRunResults(run.id, signal());
        // Re-fetch run to get updated status
        const updatedRun = await api.getRun(run.id, signal());
        setSelectedRunResults({ run: updatedRun, results });
      } catch {
        // Results may not be ready yet; that's fine
        setSelectedRunResults({ run, results: [] });
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      toast.error(err instanceof Error ? err.message : "Failed to run suite");
    } finally {
      setIsRunning(false);
    }
  };

  const handleViewRunResults = async (runId: string) => {
    setIsLoadingDetail(true);
    try {
      const [run, results] = await Promise.all([
        api.getRun(runId, signal()),
        api.getRunResults(runId, signal()),
      ]);
      setSelectedRunResults({ run, results });
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      toast.error(err instanceof Error ? err.message : "Failed to load run results");
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const handleCasesChanged = useCallback(async () => {
    if (!selectedSuiteId) return;
    try {
      const caseList = await api.listCases(selectedSuiteId, signal());
      setCases(caseList);
    } catch {
      // silent — editor shows its own toasts
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSuiteId]);

  /* ---------------------------------------------------------------- */
  /*  Render                                                          */
  /* ---------------------------------------------------------------- */

  const contentBody = (
    <div className="flex-1 flex overflow-hidden relative">
          {/* ============ Sidebar ============ */}
          <div
            className="w-72 border-r flex flex-col"
            style={{ borderColor: "var(--border-default)" }}
          >
            <div className="p-4 border-b" style={{ borderColor: "var(--border-default)" }}>
              {isCreating ? (
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newSuiteName}
                    onChange={(e) => setNewSuiteName(e.target.value)}
                    placeholder="Suite name..."
                    className="input-field flex-1 text-sm"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleCreateSuite();
                      if (e.key === "Escape") { setIsCreating(false); setNewSuiteName(""); }
                    }}
                  />
                  <button onClick={handleCreateSuite} className="btn-pill text-sm px-3" disabled={isLoadingSuites}>
                    Add
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setIsCreating(true)}
                  className="btn-pill w-full text-sm"
                  disabled={isLoadingSuites}
                >
                  <span className="flex items-center justify-center gap-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    New Suite
                  </span>
                </button>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-4" style={{ backgroundColor: "var(--bg-primary)" }}>
              {isLoadingSuites && suites.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-4 text-[var(--text-muted)]">
                  <Spinner />
                  <span className="text-sm">Loading suites…</span>
                </div>
              ) : suites.length === 0 ? (
                <div className="text-center py-4 text-[var(--text-muted)]">
                  <p className="text-sm">No eval suites yet</p>
                  <p className="text-xs mt-1">Create one to start testing your flow</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {suites.map((suite) => (
                    <div
                      key={suite.id}
                      className={`p-3 rounded-xl border-2 cursor-pointer transition-all group ${
                        selectedSuiteId === suite.id
                          ? "border-[var(--border-active)] bg-[rgba(139,148,158,0.08)]"
                          : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
                      }`}
                      style={{
                        backgroundColor: selectedSuiteId === suite.id ? undefined : "var(--bg-secondary)",
                      }}
                      onClick={() => handleSelectSuite(suite.id)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <h4 className="text-sm font-medium text-white truncate">{suite.name}</h4>
                          {suite.description && (
                            <p className="text-xs text-[var(--text-muted)] mt-0.5 truncate">
                              {suite.description}
                            </p>
                          )}
                          <p className="text-xs text-[var(--text-muted)] mt-0.5">
                            {new Date(suite.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSuite(suite.id);
                          }}
                          className="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity text-[var(--text-muted)] hover:text-red-400 hover:bg-red-500/10"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ============ Main panel ============ */}
          <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: "var(--bg-primary)" }}>
            {selectedSuite ? (
              <>
                {/* Suite header */}
                <div
                  className="p-4 border-b flex items-center justify-between"
                  style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
                >
                  <div>
                    <h3 className="text-lg font-semibold text-white">{selectedSuite.name}</h3>
                    <p className="text-xs text-[var(--text-muted)]">
                      {cases.length} case{cases.length !== 1 ? "s" : ""}
                      {" · "}
                      {runs.length} run{runs.length !== 1 ? "s" : ""}
                      {selectedSuite.created_at && (
                        <> · Created {new Date(selectedSuite.created_at).toLocaleDateString()}</>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {selectedRunResults && (
                      <button
                        onClick={() => setSelectedRunResults(null)}
                        className="btn-secondary text-sm flex items-center gap-1"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                        Back to Editor
                      </button>
                    )}
                    {/* Dataset upload */}
                    <button
                      type="button"
                      onClick={() => setShowDatasetUpload(true)}
                      className="btn-secondary text-sm flex items-center gap-1"
                      title="Upload JSONL dataset"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                      </svg>
                      Dataset
                    </button>
                    {/* Thresholds */}
                    <button
                      type="button"
                      onClick={() => setShowThresholds(true)}
                      className="btn-secondary text-sm flex items-center gap-1"
                      title="Configure pass thresholds"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                      </svg>
                      Thresholds
                    </button>
                    <button
                      onClick={handleRunSuite}
                      disabled={isRunning || cases.length === 0}
                      className="btn-pill flex items-center gap-2"
                    >
                      {isRunning ? (
                        <>
                          <Spinner />
                          Running…
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          Run Suite
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Content area */}
                <div className="flex-1 overflow-y-auto p-6">
                  {isLoadingDetail ? (
                    <div className="flex flex-col items-center gap-2 py-12 text-[var(--text-muted)]">
                      <Spinner className="w-6 h-6" />
                      <span className="text-sm">Loading…</span>
                    </div>
                  ) : selectedRunResults ? (
                    <EvalRunResults
                      run={selectedRunResults.run}
                      results={selectedRunResults.results}
                      cases={cases}
                      onViewRun={onViewRun}
                    />
                  ) : (
                    <div className="space-y-8">
                      {/* Cases section */}
                      <EvalSuiteEditor
                        suiteId={selectedSuiteId!}
                        cases={cases}
                        onCasesChanged={handleCasesChanged}
                      />

                      {/* Runs section */}
                      {runs.length > 0 && (
                        <div>
                          <h4 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
                            Recent Runs
                          </h4>
                          <div className="space-y-2">
                            {runs.map((run) => (
                              <div
                                key={run.id}
                                className="rounded-xl p-3 border flex items-center justify-between cursor-pointer transition-all hover:border-[var(--text-muted)]"
                                style={{
                                  backgroundColor: "var(--bg-secondary)",
                                  borderColor: "var(--border-default)",
                                }}
                                onClick={() => handleViewRunResults(run.id)}
                              >
                                <div className="flex items-center gap-3">
                                  <RunStatusBadge status={run.status} />
                                  <div>
                                    <p className="text-sm text-white">
                                      {run.passed_cases}/{run.total_cases} passed
                                    </p>
                                    <p className="text-xs text-[var(--text-muted)]">
                                      {new Date(run.created_at).toLocaleString()}
                                    </p>
                                  </div>
                                </div>
                                <svg className="w-4 h-4 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                </svg>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            ) : (
              /* empty state */
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <div
                    className="w-16 h-16 mx-auto mb-4 rounded-xl flex items-center justify-center"
                    style={{ backgroundColor: "var(--bg-tertiary)" }}
                  >
                    <svg className="w-8 h-8 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                  </div>
                  <p className="text-[var(--text-secondary)]">Select a suite to view and edit</p>
                  <p className="text-xs text-[var(--text-muted)] mt-1">Or create a new one from the sidebar</p>
                </div>
              </div>
            )}
          </div>
        </div>
  );

  /* Modals */
  const modals = (
    <>
      {showDatasetUpload && selectedSuiteId && (
        <DatasetUploadModal
          suiteId={selectedSuiteId}
          onClose={() => setShowDatasetUpload(false)}
          onImported={async (count) => {
            toast.success(`Imported ${count} cases from dataset`);
            setShowDatasetUpload(false);
            await handleCasesChanged();
          }}
        />
      )}
      {showThresholds && selectedSuite && (
        <ThresholdsModal
          suite={selectedSuite}
          onClose={() => setShowThresholds(false)}
          onSaved={(updatedSuite) => {
            setSuites((prev) => prev.map((s) => s.id === updatedSuite.id ? updatedSuite : s));
            setShowThresholds(false);
            toast.success("Thresholds saved");
          }}
        />
      )}
    </>
  );

  if (embedded) return <div className="h-full flex flex-col">{contentBody}{modals}</div>;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-6xl mx-4 h-[85vh] flex flex-col border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Eval Suites</h2>
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
      {modals}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Small helpers                                                     */
/* ------------------------------------------------------------------ */

function RunStatusBadge({ status }: { status: EvalRun["status"] }) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    pending: { bg: "bg-amber-500/20", text: "text-amber-400", label: "Pending" },
    running: { bg: "bg-blue-500/20", text: "text-blue-400", label: "Running" },
    completed: { bg: "bg-green-500/20", text: "text-green-400", label: "Completed" },
    failed: { bg: "bg-red-500/20", text: "text-red-400", label: "Failed" },
  };
  const s = map[status] ?? map.pending;
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  );
}
