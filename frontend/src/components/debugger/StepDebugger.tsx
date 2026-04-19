"use client";

import { useState, useCallback } from "react";
import toast from "react-hot-toast";
import { NODE_TYPE_COLORS } from "@/types/ir";
import type { NodeType } from "@/types/ir";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface DebugSessionState {
  session_id: string;
  flow_id: string;
  status: string;
  current_step: number;
  total_steps: number;
  current_node_id: string | null;
  execution_order: string[];
  context_snapshot: {
    user_input: Record<string, unknown>;
    variables: Record<string, unknown>;
    node_outputs: Record<string, unknown>;
    retrieved_docs_count: number;
  };
  step_results: Array<{
    step: number;
    node_id: string;
    node_type: string;
    status: string;
    output?: Record<string, unknown>;
    error?: string;
  }>;
  error: string | null;
}

interface StepDebuggerProps {
  flowId: string;
  onClose: () => void;
  embedded?: boolean;
}

export default function StepDebugger({ flowId, onClose, embedded }: StepDebuggerProps) {
  const [debugSession, setDebugSession] = useState<DebugSessionState | null>(null);
  const [inputJson, setInputJson] = useState('{"input": "Hello"}');
  const [isStarting, setIsStarting] = useState(false);
  const [isStepping, setIsStepping] = useState(false);
  const [selectedStep, setSelectedStep] = useState<number | null>(null);

  const startSession = useCallback(async () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(inputJson);
    } catch {
      toast.error("Invalid JSON input");
      return;
    }

    setIsStarting(true);
    try {
      const res = await fetch(`${API_BASE}/debug/flows/${flowId}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: parsed }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Failed to start debug session");
      }
      const data = await res.json();
      setDebugSession(data);
      toast.success("Debug session started");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed");
    } finally {
      setIsStarting(false);
    }
  }, [flowId, inputJson]);

  const sendCommand = useCallback(
    async (command: "step" | "continue" | "abort") => {
      if (!debugSession) return;
      setIsStepping(true);
      try {
        const res = await fetch(`${API_BASE}/debug/sessions/${debugSession.session_id}/command`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail);
        }
        const data = await res.json();
        setDebugSession(data);
        if (data.status === "completed") toast.success("Execution completed");
        if (data.status === "failed") toast.error(data.error || "Step failed");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Command failed");
      } finally {
        setIsStepping(false);
      }
    },
    [debugSession]
  );

  const currentStepResult =
    selectedStep !== null && debugSession
      ? debugSession.step_results[selectedStep]
      : null;

  const embeddedHeader = (
    <div className="px-4 py-2 border-b flex items-center gap-2 flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
      {debugSession && (
        <span
          className="text-xs px-2 py-0.5 rounded-full"
          style={{
            backgroundColor:
              debugSession.status === "paused" ? "rgba(234, 179, 8, 0.2)" :
              debugSession.status === "running" ? "rgba(59, 130, 246, 0.2)" :
              debugSession.status === "completed" ? "rgba(34, 197, 94, 0.2)" :
              "rgba(239, 68, 68, 0.2)",
            color:
              debugSession.status === "paused" ? "#eab308" :
              debugSession.status === "running" ? "#3b82f6" :
              debugSession.status === "completed" ? "#22c55e" :
              "#ef4444",
          }}
        >
          {debugSession.status} ({debugSession.current_step}/{debugSession.total_steps})
        </span>
      )}
      {debugSession && debugSession.status === "paused" && (
        <>
          <button onClick={() => sendCommand("step")} disabled={isStepping} className="btn-pill">
            {isStepping ? "..." : "Step Over"}
          </button>
          <button onClick={() => sendCommand("continue")} disabled={isStepping} className="btn-pill">
            Continue
          </button>
          <button onClick={() => sendCommand("abort")} disabled={isStepping} className="btn-pill">
            Abort
          </button>
        </>
      )}
    </div>
  );

  const contentBody = (
    <div className="flex-1 flex overflow-hidden">
          {!debugSession ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
              <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                Enter input JSON and start stepping through the flow node by node.
              </p>
              <textarea
                value={inputJson}
                onChange={(e) => setInputJson(e.target.value)}
                className="w-full max-w-md h-32 rounded-lg p-3 font-mono text-xs resize-none focus:outline-none focus:ring-1 focus:ring-[var(--border-active)]"
                style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }}
                placeholder='{"input": "Hello"}'
              />
              <button
                onClick={startSession}
                disabled={isStarting}
                className="btn-pill px-6 py-2 !text-sm"
              >
                {isStarting ? "Starting..." : "Start Debug Session"}
              </button>
            </div>
          ) : (
            <>
              <div className="w-72 border-r overflow-y-auto p-3 space-y-1 flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
                {debugSession.execution_order.map((nodeId, idx) => {
                  const result = debugSession.step_results[idx];
                  const isCurrent = idx === debugSession.current_step && debugSession.status === "paused";
                  const nodeType = result?.node_type?.toUpperCase() as NodeType | undefined;
                  const color = nodeType ? (NODE_TYPE_COLORS[nodeType] || "#64748b") : "#64748b";

                  return (
                    <button
                      key={idx}
                      onClick={() => result && setSelectedStep(idx)}
                      className={`w-full text-left rounded-lg px-3 py-2 text-xs transition-colors ${isCurrent ? "ring-1 ring-yellow-500/50" : ""}`}
                      style={{
                        backgroundColor: selectedStep === idx ? "var(--bg-tertiary)" : isCurrent ? "rgba(234, 179, 8, 0.1)" : "transparent",
                        color: result ? "var(--text-primary)" : "var(--text-muted)",
                        cursor: result ? "pointer" : "default",
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-5 h-5 flex items-center justify-center rounded-full text-[10px] font-mono" style={{ backgroundColor: `${color}20`, color }}>
                          {idx + 1}
                        </span>
                        <span className="truncate">{nodeId}</span>
                        {result && (
                          <span className="ml-auto">
                            {result.status === "completed" ? "✅" : "❌"}
                          </span>
                        )}
                        {isCurrent && !result && <span className="ml-auto text-yellow-500">→</span>}
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4" style={{ backgroundColor: "var(--bg-primary)" }}>
                <div className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}>
                  <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>CONTEXT SNAPSHOT</h3>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="font-medium" style={{ color: "var(--text-secondary)" }}>Variables:</span>
                      <pre className="mt-1 p-2 rounded text-[10px] overflow-auto max-h-24" style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}>
                        {JSON.stringify(debugSession.context_snapshot.variables, null, 2)}
                      </pre>
                    </div>
                    <div>
                      <span className="font-medium" style={{ color: "var(--text-secondary)" }}>Node Outputs:</span>
                      <pre className="mt-1 p-2 rounded text-[10px] overflow-auto max-h-24" style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}>
                        {JSON.stringify(Object.keys(debugSession.context_snapshot.node_outputs), null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>

                {currentStepResult && (
                  <div className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}>
                    <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>
                      STEP {currentStepResult.step + 1}: {currentStepResult.node_id} ({currentStepResult.node_type})
                    </h3>
                    {currentStepResult.output && (
                      <pre className="p-3 rounded text-xs overflow-auto max-h-64 font-mono" style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}>
                        {JSON.stringify(currentStepResult.output, null, 2)}
                      </pre>
                    )}
                    {currentStepResult.error && (
                      <div className="p-3 rounded text-xs text-red-400" style={{ backgroundColor: "rgba(239, 68, 68, 0.1)" }}>
                        {currentStepResult.error}
                      </div>
                    )}
                  </div>
                )}

                {debugSession.error && (
                  <div className="p-3 rounded-lg border border-red-500/30 text-xs text-red-400" style={{ backgroundColor: "rgba(239, 68, 68, 0.1)" }}>
                    {debugSession.error}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
  );

  if (embedded) return (
    <div className="h-full flex flex-col">
      {embeddedHeader}
      {contentBody}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-5xl mx-4 h-[85vh] flex flex-col border"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="p-4 border-b flex items-center justify-between flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Step Debugger</h2>
            {debugSession && (
              <span
                className="text-xs px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor:
                    debugSession.status === "paused" ? "rgba(234, 179, 8, 0.2)" :
                    debugSession.status === "running" ? "rgba(59, 130, 246, 0.2)" :
                    debugSession.status === "completed" ? "rgba(34, 197, 94, 0.2)" :
                    "rgba(239, 68, 68, 0.2)",
                  color:
                    debugSession.status === "paused" ? "#eab308" :
                    debugSession.status === "running" ? "#3b82f6" :
                    debugSession.status === "completed" ? "#22c55e" :
                    "#ef4444",
                }}
              >
                {debugSession.status} ({debugSession.current_step}/{debugSession.total_steps})
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {debugSession && debugSession.status === "paused" && (
              <>
                <button onClick={() => sendCommand("step")} disabled={isStepping} className="btn-pill">
                  {isStepping ? "..." : "Step Over"}
                </button>
                <button onClick={() => sendCommand("continue")} disabled={isStepping} className="btn-pill">
                  Continue
                </button>
                <button onClick={() => sendCommand("abort")} disabled={isStepping} className="btn-pill">
                  Abort
                </button>
              </>
            )}
            <button onClick={onClose} className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]" style={{ color: "var(--text-muted)" }}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {contentBody}
      </div>
    </div>
  );
}
