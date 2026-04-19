"use client";

import { useState } from "react";
import GroupModal from "@/components/shared/GroupModal";
import type { GroupTab } from "@/components/shared/GroupModal";
import DebuggerPanel from "@/components/debugger/DebuggerPanel";
import StepDebugger from "@/components/debugger/StepDebugger";
import BatchRunPanel from "@/components/batch/BatchRunPanel";
import LogViewer from "@/components/debugger/LogViewer";

const TABS: GroupTab[] = [
  { id: "runs", label: "Runs" },
  { id: "step", label: "Step Debug" },
  { id: "batch", label: "Batch" },
  { id: "logs", label: "Logs" },
];

interface RunDebugGroupProps {
  flowId: string;
  onClose: () => void;
  initialTab?: string;
  initialShowNewRun?: boolean;
  onOpenSettings?: (scope: "workspace" | "project") => void;
}

export default function RunDebugGroup({
  flowId,
  onClose,
  initialTab = "runs",
  initialShowNewRun = false,
  onOpenSettings,
}: RunDebugGroupProps) {
  const [activeTab, setActiveTab] = useState(initialTab);

  return (
    <GroupModal
      isOpen
      onClose={onClose}
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      title="Run & Debug"
    >
      {activeTab === "runs" && (
        <DebuggerPanel
          flowId={flowId}
          onClose={onClose}
          initialShowNewRun={initialShowNewRun}
          onOpenSettings={onOpenSettings}
          embedded
        />
      )}
      {activeTab === "step" && (
        <StepDebugger flowId={flowId} onClose={onClose} embedded />
      )}
      {activeTab === "batch" && (
        <BatchRunPanel flowId={flowId} onClose={onClose} embedded />
      )}
      {activeTab === "logs" && <LogViewer onClose={onClose} embedded />}
    </GroupModal>
  );
}
