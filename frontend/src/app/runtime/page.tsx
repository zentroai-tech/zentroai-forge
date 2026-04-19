"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import {
  approveRequest,
  createRuntimeRun,
  denyRequest,
  getRuntimeRun,
  getRuntimeRunSteps,
  getRuntimeSessionState,
  getSessionMemory,
  getToolsHealth,
  listApprovals,
  listRuntimeTools,
  pingRuntimeHealth,
  replayRun,
  summarizeSession,
} from "@/lib/api/runtime";
import { useRuntimeRunsStore } from "@/lib/runtimeRunsStore";

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function compact(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

type RuntimeTab =
  | "timeline"
  | "tools"
  | "result"
  | "metrics"
  | "approvals"
  | "replay"
  | "health"
  | "session";

const TAB_HELP: Record<RuntimeTab, string> = {
  timeline: "Execution steps for selected run",
  approvals: "Pending human approvals for this session",
  replay: "Replay selected run in deterministic play mode",
  tools: "Resolved tool catalog (local + MCP)",
  health: "Per-tool resilience: rate-limit and circuit state",
  session: "Session memory summary and counters",
  result: "Final run output payload",
  metrics: "Raw runtime metadata for debugging",
};

export default function RuntimeConsolePage() {
  const {
    currentRunId,
    runsById,
    stepsByRunId,
    toolsCatalog,
    approvalsBySessionId,
    replayByRunId,
    toolHealth,
    sessionMemoryBySessionId,
    setCurrentRunId,
    upsertRun,
    setRunSteps,
    setToolsCatalog,
    setApprovalsForSession,
    setReplayMapping,
    setToolHealth,
    setSessionMemory,
  } = useRuntimeRunsStore();

  const [entrypoint, setEntrypoint] = useState("main");
  const [inputJson, setInputJson] = useState('{\n  "input": "hi"\n}');
  const [reuseSessionId, setReuseSessionId] = useState("");
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<RuntimeTab>("timeline");
  const [sessionState, setSessionState] = useState<Record<string, unknown> | null>(null);
  const [replaySourceRunId, setReplaySourceRunId] = useState("");
  const [runtimeConnected, setRuntimeConnected] = useState<boolean>(false);
  const [runtimeStatusText, setRuntimeStatusText] = useState<string>("checking");

  const currentRun = currentRunId ? runsById[currentRunId] : null;
  const currentSteps = currentRunId ? stepsByRunId[currentRunId] || [] : [];
  const currentSessionId = currentRun?.session_id || reuseSessionId;
  const approvals = currentSessionId ? approvalsBySessionId[currentSessionId] || [] : [];

  const sortedRuns = useMemo(
    () => Object.values(runsById).sort((a, b) => b.run_id.localeCompare(a.run_id)),
    [runsById]
  );

  const entrypointOptions = useMemo(() => {
    const fromRuns = Array.from(
      new Set(
        Object.values(runsById)
          .map((r) => (r.entrypoint || "").trim())
          .filter(Boolean)
      )
    );
    return Array.from(new Set(["main", ...fromRuns]));
  }, [runsById]);

  const replaySourceOptions = useMemo(() => sortedRuns.map((r) => r.run_id), [sortedRuns]);
  const toolHealthEntries = useMemo(() => Object.entries(toolHealth || {}), [toolHealth]);

  const tabConfig = useMemo(
    () => [
      { key: "timeline" as const, enabled: Boolean(currentRunId), show: true },
      { key: "approvals" as const, enabled: Boolean(currentSessionId), show: Boolean(currentSessionId) },
      { key: "replay" as const, enabled: replaySourceOptions.length > 0, show: replaySourceOptions.length > 0 },
      { key: "tools" as const, enabled: true, show: true },
      { key: "health" as const, enabled: Object.keys(toolHealth || {}).length > 0, show: true },
      { key: "session" as const, enabled: Boolean(currentSessionId), show: true },
      { key: "result" as const, enabled: Boolean(currentRunId), show: true },
      { key: "metrics" as const, enabled: Boolean(currentRunId), show: true },
    ],
    [currentRunId, currentSessionId, replaySourceOptions.length, toolHealth]
  );

  const refreshTools = useCallback(async (): Promise<number> => {
    try {
      const tools = await listRuntimeTools();
      setToolsCatalog(tools);
      return tools.length;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load tools");
      return 0;
    }
  }, [setToolsCatalog]);

  const refreshToolHealth = useCallback(async (): Promise<number> => {
    try {
      const health = await getToolsHealth();
      setToolHealth(health.tools || {});
      return Object.keys(health.tools || {}).length;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load tool health");
      return 0;
    }
  }, [setToolHealth]);

  const refreshApprovals = useCallback(async (): Promise<number> => {
    if (!currentSessionId) {
      return -1;
    }
    try {
      const items = await listApprovals({
        status: "pending",
        session_id: currentSessionId,
      });
      setApprovalsForSession(currentSessionId, items);
      return items.length;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load approvals");
      return 0;
    }
  }, [currentSessionId, setApprovalsForSession]);

  const refreshSession = useCallback(async () => {
    if (!currentSessionId) return;
    try {
      const [state, memory] = await Promise.all([
        getRuntimeSessionState(currentSessionId),
        getSessionMemory(currentSessionId),
      ]);
      setSessionState(state);
      setSessionMemory(currentSessionId, memory);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load session");
    }
  }, [currentSessionId, setSessionMemory]);

  const refreshRun = useCallback(
    async (runId: string) => {
      if (!runId?.trim()) {
        toast.error("run_id_required");
        return;
      }
      try {
        const [run, steps] = await Promise.all([getRuntimeRun(runId), getRuntimeRunSteps(runId)]);
        upsertRun(run);
        setRunSteps(runId, steps);
        setCurrentRunId(runId);
        if (run.session_id) {
          setReuseSessionId(run.session_id);
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load run");
      }
    },
    [setCurrentRunId, setRunSteps, upsertRun]
  );

  const handleRun = async () => {
    if (!runtimeConnected) {
      toast.error("Runtime server is disconnected");
      return;
    }

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(inputJson);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("Input must be a JSON object");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Invalid JSON");
      return;
    }

    if (reuseSessionId.trim()) {
      parsed.session_id = reuseSessionId.trim();
    }

    setLoading(true);
    try {
      const run = await createRuntimeRun({ entrypoint, input: parsed });
      upsertRun(run);
      setCurrentRunId(run.run_id);
      await refreshRun(run.run_id);
      if (run.session_id) setReuseSessionId(run.session_id);
      if (run.session_id) {
        try {
          const snapshot = await summarizeSession(run.session_id);
          setSessionMemory(run.session_id, snapshot);
        } catch {
          // Summarize endpoint may be disabled (non-DEV). Ignore and keep session refresh.
        }
        await refreshSession();
        await refreshApprovals();
      }
      toast.success("Run completed");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Run failed");
    } finally {
      setLoading(false);
    }
  };

  const handleReplay = async () => {
    const sourceRunId = replaySourceRunId.trim() || currentRunId || "";
    if (!sourceRunId) {
      toast.error("Select a run first");
      return;
    }
    try {
      const replay = await replayRun({ run_id: sourceRunId, mode: "play" });
      setReplayMapping(sourceRunId, replay.replay_run_id);
      await refreshRun(replay.replay_run_id);
      toast.success(`Replay created: ${replay.replay_run_id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Replay failed");
    }
  };

  const handleApprove = async (approvalId: string) => {
    try {
      await approveRequest(approvalId);
      await refreshApprovals();
      if (currentRunId) await refreshRun(currentRunId);
      toast.success("Approved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Approval failed");
    }
  };

  const handleDeny = async (approvalId: string) => {
    try {
      await denyRequest(approvalId);
      await refreshApprovals();
      if (currentRunId) await refreshRun(currentRunId);
      toast.success("Denied");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Deny failed");
    }
  };

  const refreshRuntimeStatus = useCallback(async () => {
    const health = await pingRuntimeHealth();
    setRuntimeConnected(health.ok);
    setRuntimeStatusText(health.status);
  }, []);

  useEffect(() => {
    void refreshRuntimeStatus();
    void refreshTools();
    void refreshToolHealth();
    const timer = window.setInterval(() => {
      void refreshRuntimeStatus();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshRuntimeStatus, refreshToolHealth, refreshTools]);

  return (
    <div className="min-h-screen p-6 space-y-4" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Runtime Console</h1>
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border"
            style={{
              borderColor: runtimeConnected ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)",
              backgroundColor: runtimeConnected ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
              color: runtimeConnected ? "#86efac" : "#fca5a5",
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: runtimeConnected ? "#22c55e" : "#ef4444" }}
            />
            {runtimeConnected ? "Connected" : "Disconnected"} ({runtimeStatusText})
          </span>
          <button className="btn-secondary" onClick={() => void refreshRuntimeStatus()}>
            Retry Connection
          </button>
          <Link href="/" className="btn-secondary flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.25 19.25 3 12m0 0 7.25-7.25M3 12h18" />
            </svg>
            Back to Forge
          </Link>
          <button
            className="btn-secondary"
            onClick={async () => {
              const count = await refreshTools();
              setTab("tools");
              toast.success(`Tools refreshed: ${count}`);
            }}
          >
            Refresh Tools
          </button>
          <button
            className="btn-secondary"
            onClick={async () => {
              const count = await refreshToolHealth();
              setTab("health");
              if (count === 0) toast("No tool health data yet");
              else toast.success(`Tool health updated: ${count}`);
            }}
          >
            Tool Health
          </button>
          <button
            className="btn-secondary"
            onClick={async () => {
              const count = await refreshApprovals();
              setTab("approvals");
              if (count < 0) {
                toast("Run first or select a session to load approvals");
              } else {
                toast.success(`Pending approvals: ${count}`);
              }
            }}
          >
            Approvals
          </button>
          <button className="btn-secondary" onClick={() => void refreshSession()}>Session</button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <section
          className="col-span-12 lg:col-span-4 rounded-xl border p-4 space-y-3"
          style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
        >
          <h2 className="text-sm font-semibold text-white">Run Request</h2>

          <label className="block text-xs" style={{ color: "var(--text-secondary)" }} title="Entrypoint sent to POST /runs">
            Entrypoint
          </label>
          <select className="input-field w-full" value={entrypoint} onChange={(e) => setEntrypoint(e.target.value)}>
            {entrypointOptions.map((ep) => (
              <option key={ep} value={ep}>{ep}</option>
            ))}
          </select>

          <label className="block text-xs" style={{ color: "var(--text-secondary)" }} title='JSON payload sent as "input"'>
            Input JSON
          </label>
          <textarea
            className="input-field w-full min-h-[160px] font-mono text-xs"
            value={inputJson}
            onChange={(e) => setInputJson(e.target.value)}
          />

          <label className="block text-xs" style={{ color: "var(--text-secondary)" }} title="Reuse previous session to keep memory/state">
            Session ID (reuse)
          </label>
          <input
            className="input-field w-full"
            value={reuseSessionId}
            onChange={(e) => setReuseSessionId(e.target.value)}
            placeholder="session_xxx"
          />

          <div className="grid grid-cols-2 gap-2">
            <button
              className="btn-pill disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={() => void handleRun()}
              disabled={loading || !runtimeConnected}
              title={!runtimeConnected ? "Runtime server unreachable" : "Execute run"}
            >
              {loading ? "Running..." : "Run"}
            </button>
            <button
              className="btn-secondary"
              onClick={() => void handleReplay()}
              disabled={!runtimeConnected || replaySourceOptions.length === 0}
              title={!runtimeConnected ? "Runtime server unreachable" : "Replay selected run"}
            >
              Replay
            </button>
          </div>

          <label className="block text-xs" style={{ color: "var(--text-secondary)" }} title="Pick a completed run to replay">
            Replay source run_id
          </label>
          <select
            className="input-field w-full"
            value={replaySourceRunId}
            onChange={(e) => setReplaySourceRunId(e.target.value)}
          >
            <option value="">Select run</option>
            {replaySourceOptions.map((runId) => (
              <option key={runId} value={runId}>{runId}</option>
            ))}
          </select>

          {currentRun && (
            <div className="rounded-lg border p-2 text-xs" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
              <div>run_id: {currentRun.run_id}</div>
              <div>trace_id: {currentRun.trace_id || "-"}</div>
              <div>session_id: {currentRun.session_id || "-"}</div>
              <div>status: {currentRun.status}</div>
              {currentRun.replay_of && <div className="text-amber-300">REPLAY of: {currentRun.replay_of}</div>}
              {currentRunId && replayByRunId[currentRunId] && <div className="text-amber-300">replay_run_id: {replayByRunId[currentRunId]}</div>}
            </div>
          )}
        </section>

        <section
          className="col-span-12 lg:col-span-8 rounded-xl border p-4"
          style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
        >
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {tabConfig.filter((cfg) => cfg.show).map(({ key, enabled }) => (
              <button
                key={key}
                className="px-3 py-1.5 rounded-lg text-xs border"
                style={{
                  borderColor: key === tab ? "var(--border-active)" : "var(--border-default)",
                  backgroundColor: key === tab ? "var(--bg-selected)" : "transparent",
                  color: key === tab ? "var(--text-primary)" : enabled ? "var(--text-secondary)" : "var(--text-muted)",
                  opacity: enabled ? 1 : 0.55,
                }}
                onClick={() => {
                  if (!enabled) return;
                  setTab(key);
                }}
                title={TAB_HELP[key]}
                disabled={!enabled}
              >
                {key}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-12 gap-3">
            <div className="col-span-12 xl:col-span-4 space-y-2 max-h-[460px] overflow-auto pr-1">
              <h3 className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Runs</h3>
              {sortedRuns.map((run) => (
                <button
                  key={run.run_id}
                  onClick={() => void refreshRun(run.run_id)}
                  className="w-full text-left rounded-lg border p-2"
                  style={{
                    borderColor: run.run_id === currentRunId ? "var(--border-active)" : "var(--border-default)",
                    backgroundColor: run.run_id === currentRunId ? "var(--bg-selected)" : "transparent",
                  }}
                >
                  <div className="text-xs text-white">{run.run_id}</div>
                  <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {run.status} {run.session_id ? ` | ${run.session_id}` : ""}
                  </div>
                  {run.replay_of && <div className="text-[11px] text-amber-300">REPLAY</div>}
                </button>
              ))}
              {sortedRuns.length === 0 && <p className="text-xs" style={{ color: "var(--text-muted)" }}>No runs yet.</p>}
            </div>

            <div className="col-span-12 xl:col-span-8">
              {tab === "timeline" && (
                currentSteps.length === 0
                  ? <p className="text-xs" style={{ color: "var(--text-muted)" }}>Select a run to view timeline steps.</p>
                  : (
                    <div className="space-y-2 max-h-[420px] overflow-auto pr-1">
                      {currentSteps.map((step, index) => (
                        <div
                          key={step.step_id || `${index}`}
                          className="rounded-lg border p-2 text-xs"
                          style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-white font-medium">{step.step_id || `step_${index + 1}`}</div>
                            <div
                              className="px-2 py-0.5 rounded-full text-[11px] border"
                              style={{
                                borderColor: step.status === "completed" ? "rgba(34,197,94,0.3)" : "var(--border-default)",
                                color: step.status === "completed" ? "#86efac" : "var(--text-secondary)",
                              }}
                            >
                              {step.status}
                            </div>
                          </div>
                          <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1" style={{ color: "var(--text-secondary)" }}>
                            <div>node: {step.node_type || "-"}</div>
                            <div>tool: {step.tool_name || "-"}</div>
                            <div>replay: {step.replay_substituted ? "yes" : "no"}</div>
                            <div>output: {compact(step.output).slice(0, 90)}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )
              )}

              {tab === "approvals" && (
                <div className="space-y-2 max-h-[420px] overflow-auto">
                  {approvals.length === 0 ? (
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>No pending approvals for this session.</p>
                  ) : (
                    approvals.map((item) => (
                      <div key={item.approval_id} className="rounded-lg border p-2 text-xs" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
                        <div className="text-white">{item.tool_name}</div>
                        <div>{item.approval_id}</div>
                        <div className="mb-2">status: {item.status}</div>
                        <div className="flex gap-2">
                          <button className="btn-pill text-xs" onClick={() => void handleApprove(item.approval_id)}>Approve</button>
                          <button className="btn-secondary text-xs" onClick={() => void handleDeny(item.approval_id)}>Deny</button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {tab === "replay" && (
                replaySourceOptions.length === 0
                  ? <p className="text-xs" style={{ color: "var(--text-muted)" }}>No runs available to replay yet.</p>
                  : (
                    <div className="space-y-2 text-xs max-h-[420px] overflow-auto pr-1">
                      <div className="rounded-lg border p-2" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
                        <div>current run: <span className="text-white">{currentRunId || "-"}</span></div>
                        <div>replay source: <span className="text-white">{replaySourceRunId || currentRunId || "-"}</span></div>
                        <div>steps substituted: <span className="text-white">{currentSteps.filter((s) => Boolean(s.replay_substituted)).length}</span></div>
                      </div>
                      <div className="rounded-lg border p-2" style={{ borderColor: "var(--border-default)" }}>
                        <div className="mb-1 font-medium text-white">Replay map</div>
                        <pre style={{ color: "var(--text-secondary)" }}>{pretty(replayByRunId)}</pre>
                      </div>
                    </div>
                  )
              )}

              {tab === "tools" && (
                toolsCatalog.length === 0
                  ? <p className="text-xs" style={{ color: "var(--text-muted)" }}>Tool catalog is empty. Press Refresh Tools.</p>
                  : (
                    <div className="rounded-lg border max-h-[420px] overflow-auto" style={{ borderColor: "var(--border-default)" }}>
                      <table className="w-full text-xs">
                        <thead>
                          <tr style={{ color: "var(--text-muted)" }}>
                            <th className="text-left p-2">name</th>
                            <th className="text-left p-2">adapter</th>
                            <th className="text-left p-2">timeout</th>
                            <th className="text-left p-2">retries</th>
                            <th className="text-left p-2">approval</th>
                          </tr>
                        </thead>
                        <tbody>
                          {toolsCatalog.map((tool) => (
                            <tr key={tool.name} style={{ borderTop: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                              <td className="p-2 text-white">{tool.name}</td>
                              <td className="p-2">{tool.adapter}</td>
                              <td className="p-2">{tool.timeout_s}s</td>
                              <td className="p-2">{tool.max_retries}</td>
                              <td className="p-2">{tool.requires_approval ? "yes" : "no"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
              )}

              {tab === "health" && (
                toolHealthEntries.length === 0
                  ? <p className="text-xs" style={{ color: "var(--text-muted)" }}>No health data yet. Execute a run with tools and press Tool Health.</p>
                  : (
                    <div className="space-y-2 max-h-[420px] overflow-auto pr-1">
                      {toolHealthEntries.map(([toolName, health]) => (
                        <div key={toolName} className="rounded-lg border p-2 text-xs" style={{ borderColor: "var(--border-default)" }}>
                          <div className="text-white font-medium">{toolName}</div>
                          <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-1" style={{ color: "var(--text-secondary)" }}>
                            <div>allowed: {health.rate_limit.allowed}</div>
                            <div>denied: {health.rate_limit.denied}</div>
                            <div>circuit open: {health.circuit.open ? "yes" : "no"}</div>
                            <div>failures: {health.circuit.failures}</div>
                            <div>cooldown: {health.circuit.cooldown_s}s</div>
                            <div>remaining: {health.circuit.remaining_cooldown_s}s</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )
              )}

              {tab === "session" && (
                <div className="space-y-2">
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Session summary updates automatically after each run.
                  </p>
                  {(() => {
                    const snapshot = currentSessionId
                      ? sessionMemoryBySessionId[currentSessionId] || { session_id: currentSessionId, summary: [], raw_count: 0 }
                      : { session_id: "", summary: [], raw_count: 0 };
                    return (
                      <div className="space-y-2">
                        <div className="rounded-lg border p-2 text-xs" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
                          <div>session_id: <span className="text-white">{snapshot.session_id || "-"}</span></div>
                          <div>raw_count: <span className="text-white">{snapshot.raw_count}</span></div>
                          <div>summary_items: <span className="text-white">{snapshot.summary.length}</span></div>
                        </div>
                        <div className="rounded-lg border p-2 text-xs max-h-[280px] overflow-auto" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
                          {snapshot.summary.length === 0 ? (
                            <p style={{ color: "var(--text-muted)" }}>No summarized items yet.</p>
                          ) : (
                            <pre>{pretty(snapshot.summary)}</pre>
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}

              {tab === "result" && (
                !currentRun
                  ? <p className="text-xs" style={{ color: "var(--text-muted)" }}>Select a run to inspect result payload.</p>
                  : (
                    <div className="space-y-2">
                      <div className="rounded-lg border p-2 text-xs" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
                        <div>run_id: <span className="text-white">{currentRun.run_id}</span></div>
                        <div>status: <span className="text-white">{currentRun.status}</span></div>
                        <div>entrypoint: <span className="text-white">{currentRun.entrypoint || "-"}</span></div>
                      </div>
                      <pre className="rounded-lg border p-3 text-xs max-h-[330px] overflow-auto" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
                        {pretty(currentRun?.result || {})}
                      </pre>
                    </div>
                  )
              )}

              {tab === "metrics" && (
                !currentRun
                  ? <p className="text-xs" style={{ color: "var(--text-muted)" }}>Select a run to inspect runtime metrics metadata.</p>
                  : (
                    <pre className="rounded-lg border p-3 text-xs max-h-[420px] overflow-auto" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
                      {pretty({
                        run_id: currentRun?.run_id || "",
                        trace_id: currentRun?.trace_id || "",
                        session_id: currentRun?.session_id || "",
                        session_state: sessionState,
                      })}
                    </pre>
                  )
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
