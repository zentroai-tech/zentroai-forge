"use client";

import { useState, useEffect } from "react";
import RunsList from "./RunsList";
import RunTimeline from "./RunTimeline";
import RunDiff from "./RunDiff";
import { listRuns } from "@/lib/api";
import type { RunListItem } from "@/types/ir";

interface DebuggerPanelProps {
  flowId: string;
  onClose: () => void;
  initialShowNewRun?: boolean;
  onOpenSettings?: (scope: "workspace" | "project") => void;
  embedded?: boolean;
}

type DebugTab = "timeline" | "diff";

export default function DebuggerPanel({ flowId, onClose, initialShowNewRun = false, onOpenSettings, embedded }: DebuggerPanelProps) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [activeTab, setActiveTab] = useState<DebugTab>("timeline");
  const [allRuns, setAllRuns] = useState<RunListItem[]>([]);

  // Keep allRuns in sync so RunDiff can populate its selectors
  useEffect(() => {
    listRuns(flowId).then(setAllRuns).catch(() => {});
  }, [flowId, refreshKey]);

  const handleRunDeleted = (deletedRunId: string) => {
    setSelectedRunId(null);
    setRefreshKey((k) => k + 1);
  };

  const tabBtnCls = (tab: DebugTab) =>
    `px-3 py-1.5 text-xs rounded-md transition-colors ${
      activeTab === tab
        ? "bg-[var(--bg-tertiary)] text-white"
        : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
    }`;

  const content = (
    <div className="flex-1 flex flex-col overflow-hidden h-full">
      {/* Tab bar */}
      <div
        className="flex items-center gap-1 px-3 py-2 border-b flex-shrink-0"
        style={{ borderColor: "var(--border-default)" }}
      >
        <button type="button" className={tabBtnCls("timeline")} onClick={() => setActiveTab("timeline")}>
          Timeline
        </button>
        <button type="button" className={tabBtnCls("diff")} onClick={() => setActiveTab("diff")}>
          Diff
        </button>
      </div>

      {activeTab === "timeline" ? (
        <div className="flex-1 flex overflow-hidden">
          {/* Runs list */}
          <div className="w-80 border-r flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
            <RunsList
              key={refreshKey}
              flowId={flowId}
              onSelectRun={setSelectedRunId}
              selectedRunId={selectedRunId}
              initialShowNewRun={initialShowNewRun}
            />
          </div>

          {/* Run detail */}
          <div className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden" style={{ backgroundColor: "var(--bg-primary)" }}>
            {selectedRunId ? (
              <RunTimeline
                runId={selectedRunId}
                onNavigateToRun={setSelectedRunId}
                onOpenSettings={onOpenSettings}
                onRunDeleted={handleRunDeleted}
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <p style={{ color: "var(--text-muted)" }}>Select a run to view details</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden" style={{ backgroundColor: "var(--bg-primary)" }}>
          <RunDiff runs={allRuns} />
        </div>
      )}
    </div>
  );

  if (embedded) return content;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-5xl mx-4 h-[80vh] flex flex-col border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Flow Runs</h2>
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

        {content}
      </div>
    </div>
  );
}
