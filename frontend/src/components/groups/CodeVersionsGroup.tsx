"use client";

import { useState } from "react";
import GroupModal from "@/components/shared/GroupModal";
import type { GroupTab } from "@/components/shared/GroupModal";
import CodePreviewTab from "@/components/code/CodePreviewTab";
import FlowVersionHistory from "@/components/flow/FlowVersionHistory";

const TABS: GroupTab[] = [
  { id: "code", label: "Code" },
  { id: "versions", label: "Versions" },
];

interface CodeVersionsGroupProps {
  flowId: string;
  onClose: () => void;
  initialTab?: string;
}

export default function CodeVersionsGroup({
  flowId,
  onClose,
  initialTab = "code",
}: CodeVersionsGroupProps) {
  const [activeTab, setActiveTab] = useState(initialTab);

  return (
    <GroupModal
      isOpen
      onClose={onClose}
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      title="Code & Versions"
    >
      {activeTab === "code" && (
        <CodePreviewTab isOpen onClose={onClose} embedded />
      )}
      {activeTab === "versions" && (
        <FlowVersionHistory flowId={flowId} onClose={onClose} embedded />
      )}
    </GroupModal>
  );
}
