"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { useFlowStore } from "@/lib/store";
import DebuggerPanel from "@/components/debugger/DebuggerPanel";
import StepDebugger from "@/components/debugger/StepDebugger";
import BatchRunPanel from "@/components/batch/BatchRunPanel";
import LogViewer from "@/components/debugger/LogViewer";
import ChatPlayground from "@/components/chat/ChatPlayground";
import PromptPlayground from "@/components/debugger/PromptPlayground";
import FlowEvalsPage from "@/components/eval/FlowEvalsPage";
import CodePreviewTab from "@/components/code/CodePreviewTab";
import FlowVersionHistory from "@/components/flow/FlowVersionHistory";

const DEFAULT_HEIGHT = 320;
const MIN_HEIGHT = 180;
// Drag can go up to 90% of viewport; the maximize button goes to viewport - toolbar (64px)
const MAX_DRAG_RATIO = 0.9;

const GROUP_LABELS: Record<"run" | "test" | "code", string> = {
  run: "Run & Debug",
  test: "Test & Evals",
  code: "Code & Versions",
};

const GROUP_TABS: Record<"run" | "test" | "code", Array<{ id: string; label: string }>> = {
  run: [
    { id: "runs", label: "Runs" },
    { id: "step", label: "Step Debug" },
    { id: "batch", label: "Batch" },
    { id: "logs", label: "Logs" },
  ],
  test: [
    { id: "chat", label: "Chat" },
    { id: "prompt", label: "Prompt" },
    { id: "evals", label: "Evals" },
  ],
  code: [
    { id: "code", label: "Code" },
    { id: "versions", label: "Versions" },
  ],
};

interface BottomDockProps {
  activeGroup: "run" | "test" | "code" | null;
  activeTab: string | undefined;
  flowId: string;
  initialShowNewRun?: boolean;
  onClose: () => void;
  onTabChange: (tab: string) => void;
  onOpenSettings?: (scope: "workspace" | "project") => void;
  onViewRun?: (runId: string) => void;
}

export default function BottomDock({
  activeGroup,
  activeTab,
  flowId,
  initialShowNewRun,
  onClose,
  onTabChange,
  onOpenSettings,
  onViewRun,
}: BottomDockProps) {
  const { openBottomDock } = useFlowStore();
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const [isMaximized, setIsMaximized] = useState(false);
  const prevHeight = useRef(DEFAULT_HEIGHT);
  const isDragging = useRef(false);
  const startY = useRef(0);
  const startHeight = useRef(0);

  // Escape key closes
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleToggleMaximize = useCallback(() => {
    if (isMaximized) {
      setHeight(prevHeight.current);
      setIsMaximized(false);
    } else {
      prevHeight.current = height;
      // Maximize to full viewport minus the toolbar height (64px)
      setHeight(window.innerHeight - 64);
      setIsMaximized(true);
    }
  }, [isMaximized, height]);

  if (!activeGroup) return null;

  const tabs = GROUP_TABS[activeGroup];
  const currentTab = activeTab && tabs.some((t) => t.id === activeTab) ? activeTab : tabs[0].id;

  const handleDragStart = (e: React.MouseEvent) => {
    // Dragging exits maximized state
    if (isMaximized) setIsMaximized(false);
    isDragging.current = true;
    startY.current = e.clientY;
    startHeight.current = height;

    const onMove = (ev: MouseEvent) => {
      if (!isDragging.current) return;
      const delta = startY.current - ev.clientY;
      const maxH = Math.floor(window.innerHeight * MAX_DRAG_RATIO);
      const newH = Math.max(MIN_HEIGHT, Math.min(maxH, startHeight.current + delta));
      setHeight(newH);
    };
    const onUp = () => {
      isDragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <div
      className="border-t flex flex-col flex-shrink-0"
      style={{
        height: `${height}px`,
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-default)",
      }}
    >
      {/* Drag handle */}
      <div
        className="h-1.5 w-full cursor-row-resize flex-shrink-0 transition-colors hover:bg-[var(--border-active)]"
        style={{ backgroundColor: "var(--border-default)" }}
        onMouseDown={handleDragStart}
      />

      {/* Tab bar */}
      <div
        className="flex items-center border-b flex-shrink-0"
        style={{ borderColor: "var(--border-default)" }}
      >
        {/* Outer group tabs */}
        <div
          className="flex items-center border-r flex-shrink-0"
          style={{ borderColor: "var(--border-default)" }}
        >
          {(["run", "test", "code"] as const).map((group) => (
            <button
              key={group}
              onClick={() => openBottomDock(group)}
              className="relative px-3 py-2 text-xs font-medium transition-colors"
              style={{
                color: activeGroup === group ? "var(--text-primary)" : "var(--text-muted)",
              }}
            >
              {GROUP_LABELS[group]}
              {activeGroup === group && (
                <span
                  className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                  style={{ backgroundColor: "var(--accent-primary)" }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Inner tabs for active group */}
        <div className="flex items-center flex-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className="relative px-3 py-2 text-xs transition-colors"
              style={{
                color: currentTab === tab.id ? "var(--text-primary)" : "var(--text-muted)",
              }}
            >
              {tab.label}
              {currentTab === tab.id && (
                <span
                  className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                  style={{ backgroundColor: "var(--text-secondary)" }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Maximize / restore button */}
        <button
          onClick={handleToggleMaximize}
          className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)] flex-shrink-0"
          style={{ color: "var(--text-muted)" }}
          aria-label={isMaximized ? "Restore panel" : "Maximize panel"}
          title={isMaximized ? "Restore" : "Maximize"}
        >
          {isMaximized ? (
            /* Restore icon — two overlapping squares collapsing inward */
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9V4H4v5h5zm0 0v5h5v-5H9zm6-5h5v5h-5V4zm0 11h5v5h-5v-5zM4 15h5v5H4v-5z" />
            </svg>
          ) : (
            /* Maximize icon — arrows pointing outward */
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" />
            </svg>
          )}
        </button>

        {/* Close button */}
        <button
          onClick={onClose}
          className="p-1.5 mr-2 rounded-md transition-colors hover:bg-[var(--bg-tertiary)] flex-shrink-0"
          style={{ color: "var(--text-muted)" }}
          aria-label="Close panel"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-hidden">
        {activeGroup === "run" && (
          <>
            {currentTab === "runs" && (
              <DebuggerPanel
                flowId={flowId}
                onClose={onClose}
                initialShowNewRun={initialShowNewRun}
                onOpenSettings={onOpenSettings}
                embedded
              />
            )}
            {currentTab === "step" && (
              <StepDebugger flowId={flowId} onClose={onClose} embedded />
            )}
            {currentTab === "batch" && (
              <BatchRunPanel flowId={flowId} onClose={onClose} embedded />
            )}
            {currentTab === "logs" && <LogViewer onClose={onClose} embedded />}
          </>
        )}

        {activeGroup === "test" && (
          <>
            {currentTab === "chat" && (
              <ChatPlayground flowId={flowId} onClose={onClose} embedded />
            )}
            {currentTab === "prompt" && (
              <PromptPlayground flowId={flowId} onClose={onClose} embedded />
            )}
            {currentTab === "evals" && (
              <FlowEvalsPage
                flowId={flowId}
                onViewRun={onViewRun ?? (() => {})}
                onClose={onClose}
                embedded
              />
            )}
          </>
        )}

        {activeGroup === "code" && (
          <>
            {currentTab === "code" && (
              <CodePreviewTab isOpen onClose={onClose} embedded />
            )}
            {currentTab === "versions" && (
              <FlowVersionHistory flowId={flowId} onClose={onClose} embedded />
            )}
          </>
        )}
      </div>
    </div>
  );
}
