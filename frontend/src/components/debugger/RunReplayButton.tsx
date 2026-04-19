"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import { replayRun, type ReplayMode } from "@/lib/api";

interface RunReplayButtonProps {
  runId: string;
  onReplayCreated: (newRunId: string) => void;
}

export default function RunReplayButton({ runId, onReplayCreated }: RunReplayButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedMode, setSelectedMode] = useState<ReplayMode>("exact");

  const handleReplay = async () => {
    setIsLoading(true);
    try {
      const newRun = await replayRun(runId, selectedMode);
      toast.success("Replay started");
      setIsOpen(false);
      onReplayCreated(newRun.id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to start replay");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="btn-secondary flex items-center gap-2 text-sm"
        disabled={isLoading}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Replay
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown */}
          <div
            className="absolute right-0 top-full mt-2 w-72 rounded-xl shadow-xl border z-50"
            style={{
              backgroundColor: "var(--bg-secondary)",
              borderColor: "var(--border-default)",
            }}
          >
            <div className="p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Replay Run</h3>

              <div className="space-y-2 mb-4">
                <label
                  className={`flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-all ${
                    selectedMode === "exact"
                      ? "border-cyan-500 bg-cyan-500/10"
                      : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
                  }`}
                  onClick={() => setSelectedMode("exact")}
                >
                  <input
                    type="radio"
                    name="replayMode"
                    checked={selectedMode === "exact"}
                    onChange={() => setSelectedMode("exact")}
                    className="mt-0.5 accent-cyan-500"
                  />
                  <div>
                    <div className="text-sm font-medium text-white">Replay Exact</div>
                    <div className="text-xs text-[var(--text-muted)] mt-0.5">
                      Re-run live with the same input and current flow state
                    </div>
                  </div>
                </label>

                <label
                  className={`flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-all ${
                    selectedMode === "mock_tools"
                      ? "border-cyan-500 bg-cyan-500/10"
                      : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
                  }`}
                  onClick={() => setSelectedMode("mock_tools")}
                >
                  <input
                    type="radio"
                    name="replayMode"
                    checked={selectedMode === "mock_tools"}
                    onChange={() => setSelectedMode("mock_tools")}
                    className="mt-0.5 accent-cyan-500"
                  />
                  <div>
                    <div className="text-sm font-medium text-white">Mock Tools Only</div>
                    <div className="text-xs text-[var(--text-muted)] mt-0.5">
                      Re-run LLMs live, mock tool executions
                    </div>
                  </div>
                </label>

                <label
                  className={`flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-all ${
                    selectedMode === "mock_all"
                      ? "border-cyan-500 bg-cyan-500/10"
                      : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
                  }`}
                  onClick={() => setSelectedMode("mock_all")}
                >
                  <input
                    type="radio"
                    name="replayMode"
                    checked={selectedMode === "mock_all"}
                    onChange={() => setSelectedMode("mock_all")}
                    className="mt-0.5 accent-cyan-500"
                  />
                  <div>
                    <div className="text-sm font-medium text-white">Mock All</div>
                    <div className="text-xs text-[var(--text-muted)] mt-0.5">
                      Deterministic replay using cached outputs (LLMs + tools)
                    </div>
                  </div>
                </label>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setIsOpen(false)}
                  className="flex-1 btn-secondary text-sm"
                  disabled={isLoading}
                >
                  Cancel
                </button>
                <button
                  onClick={handleReplay}
                  className="flex-1 btn-pill text-sm"
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Starting...
                    </span>
                  ) : (
                    "Start Replay"
                  )}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
