"use client";

import React from "react";
import { useState, useEffect, useCallback, useMemo } from "react";
import toast from "react-hot-toast";
import { listRuns, createRun, deleteAllRuns } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { useFlowStore } from "@/lib/store";
import type { RunListItem } from "@/types/ir";

interface RunsListProps {
  flowId: string;
  onSelectRun: (runId: string) => void;
  selectedRunId: string | null;
  initialShowNewRun?: boolean;
}

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  pending: { bg: "rgba(234, 179, 8, 0.2)", text: "#facc15" },
  running: { bg: "rgba(59, 130, 246, 0.2)", text: "#60a5fa" },
  completed: { bg: "rgba(34, 197, 94, 0.2)", text: "#4ade80" },
  failed: { bg: "rgba(239, 68, 68, 0.2)", text: "#f87171" },
  cancelled: { bg: "rgba(148, 163, 184, 0.2)", text: "#94a3b8" },
};

export default function RunsList({ flowId, onSelectRun, selectedRunId, initialShowNewRun = false }: RunsListProps) {
  const currentFlow = useFlowStore((s) => s.currentFlow);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showNewRun, setShowNewRun] = useState(initialShowNewRun);
  const [newRunInput, setNewRunInput] = useState("");
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [selectedEntrypoint, setSelectedEntrypoint] = useState("main");

  const isV2Flow =
    currentFlow?.id === flowId &&
    Array.isArray(currentFlow?.agents) &&
    currentFlow.agents.length > 0;
  const entrypointOptions = useMemo(
    () => (
      isV2Flow
        ? (currentFlow?.entrypoints?.map((ep) => ep.name) ?? ["main"])
        : []
    ),
    [currentFlow?.entrypoints, isV2Flow]
  );
  const canRunV2 = !isV2Flow || entrypointOptions.length > 0;

  useEffect(() => {
    if (entrypointOptions.length > 0) {
      setSelectedEntrypoint((prev) =>
        entrypointOptions.includes(prev) ? prev : entrypointOptions[0]
      );
    } else {
      setSelectedEntrypoint("main");
    }
  }, [entrypointOptions]);

  const loadRuns = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listRuns(flowId);
      setRuns(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load runs");
    } finally {
      setIsLoading(false);
    }
  }, [flowId]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const handleCreateRun = async () => {
    if (!canRunV2) {
      toast.error("This multi-agent flow has no entrypoints. Define one first.");
      return;
    }
    // Parse input as JSON or use as simple text input
    let inputData: Record<string, unknown>;
    try {
      inputData = newRunInput.trim() ? JSON.parse(newRunInput) : {};
    } catch {
      // If not valid JSON, treat as simple text input
      inputData = { input: newRunInput };
    }

    setIsLoading(true);
    try {
      const run = await createRun(
        flowId,
        inputData,
        isV2Flow ? selectedEntrypoint : undefined
      );
      toast.success("Run created");
      setShowNewRun(false);
      setNewRunInput("");
      // Add new run to the list
      setRuns((prev) => [{
        id: run.id,
        flow_id: run.flow_id,
        status: run.status,
        created_at: run.created_at,
        started_at: run.started_at,
        finished_at: run.finished_at
      }, ...prev]);
      onSelectRun(run.id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create run");
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearAll = async () => {
    try {
      const result = await deleteAllRuns(flowId);
      setRuns([]);
      onSelectRun("");
      setShowClearConfirm(false);
      toast.success(`${result.deleted} runs deleted`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to clear runs");
    }
  };

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: "var(--bg-secondary)" }}>
      <div
        className="p-4 border-b"
        style={{ borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-white">Runs</h3>
          <div className="flex items-center gap-2">
            {runs.length > 0 && !showClearConfirm && (
              <button
                onClick={() => setShowClearConfirm(true)}
                className="p-1.5 rounded-md transition-colors hover:bg-red-500/20"
                style={{ color: "var(--text-muted)" }}
                title="Clear all runs"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
            {showClearConfirm && (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-red-400 whitespace-nowrap">Clear all?</span>
                <button
                  onClick={handleClearAll}
                  className="text-xs px-2 py-1 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                >
                  Yes
                </button>
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="text-xs px-2 py-1 rounded-lg transition-colors"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
                >
                  No
                </button>
              </div>
            )}
            <button
              onClick={loadRuns}
              disabled={isLoading}
              className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
              style={{ color: "var(--text-muted)" }}
              title="Refresh"
            >
              <svg className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <button
              onClick={() => setShowNewRun(true)}
              className="btn-pill text-sm flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              New Run
            </button>
          </div>
        </div>

        {showNewRun && (
          <div
            className="p-3 rounded-lg mb-4"
            style={{ backgroundColor: "var(--bg-tertiary)" }}
          >
            {isV2Flow && entrypointOptions.length > 0 && (
              <div className="mb-3">
                <label
                  className="block text-xs font-medium mb-1"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Entrypoint
                </label>
                <select
                  value={selectedEntrypoint}
                  onChange={(e) => setSelectedEntrypoint(e.target.value)}
                  className="input-field w-full"
                >
                  {entrypointOptions.map((entrypoint) => (
                    <option key={entrypoint} value={entrypoint}>
                      {entrypoint}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--text-secondary)" }}
            >
              Input (JSON)
            </label>
            <textarea
              value={newRunInput}
              onChange={(e) => setNewRunInput(e.target.value)}
              className="input-field min-h-[80px] resize-y font-mono text-sm mb-2"
              placeholder='{"input": "Hello, how can you help me?"}'
            />
            <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
              Enter JSON input for the flow. Simple text will be wrapped as {`{"input": "..."}`}
            </p>
            {!canRunV2 && (
              <p className="text-xs mb-2 text-red-300">
                No entrypoints configured. Open Entrypoints and create at least one.
              </p>
            )}
            <div className="flex gap-2">
              <button onClick={handleCreateRun} disabled={isLoading || !canRunV2} className="btn-pill text-sm flex-1 flex items-center justify-center gap-1.5">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
                </svg>
                {isLoading ? "Running..." : "Run"}
              </button>
              <button onClick={() => setShowNewRun(false)} className="btn-secondary text-sm">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4" style={{ backgroundColor: "var(--bg-primary)" }}>
        {runs.length === 0 ? (
          <p className="text-sm text-center py-4" style={{ color: "var(--text-muted)" }}>No runs yet</p>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => {
              const statusColor = STATUS_COLORS[run.status] || STATUS_COLORS.pending;
              return (
                <button
                  key={run.id}
                  onClick={() => onSelectRun(run.id)}
                  disabled={isLoading}
                  className="w-full text-left p-3 rounded-xl border-2 transition-all"
                  style={{
                    backgroundColor: selectedRunId === run.id
                      ? "rgba(139, 148, 158, 0.08)"
                      : "var(--bg-secondary)",
                    borderColor: selectedRunId === run.id
                      ? "var(--border-active)"
                      : "var(--border-default)",
                  }}
                  onMouseEnter={(e) => {
                    if (selectedRunId !== run.id) {
                      e.currentTarget.style.borderColor = "var(--text-muted)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedRunId !== run.id) {
                      e.currentTarget.style.borderColor = "var(--border-default)";
                    }
                  }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      {run.id.length > 20 ? `${run.id.slice(0, 20)}...` : run.id}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{ backgroundColor: statusColor.bg, color: statusColor.text }}
                    >
                      {run.status}
                    </span>
                  </div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {formatDate(run.created_at)}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
