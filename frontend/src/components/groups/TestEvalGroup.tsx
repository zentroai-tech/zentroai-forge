"use client";

import { useState } from "react";
import GroupModal from "@/components/shared/GroupModal";
import type { GroupTab } from "@/components/shared/GroupModal";
import ChatPlayground from "@/components/chat/ChatPlayground";
import PromptPlayground from "@/components/debugger/PromptPlayground";
import FlowEvalsPage from "@/components/eval/FlowEvalsPage";

const TABS: GroupTab[] = [
  { id: "chat", label: "Chat" },
  { id: "prompt", label: "Prompt" },
  { id: "evals", label: "Evals" },
];

interface TestEvalGroupProps {
  flowId: string;
  onClose: () => void;
  initialTab?: string;
  onViewRun?: (runId: string) => void;
}

export default function TestEvalGroup({
  flowId,
  onClose,
  initialTab = "chat",
  onViewRun,
}: TestEvalGroupProps) {
  const [activeTab, setActiveTab] = useState(initialTab);

  return (
    <GroupModal
      isOpen
      onClose={onClose}
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      title="Test & Eval"
    >
      {activeTab === "chat" && (
        <ChatPlayground flowId={flowId} onClose={onClose} embedded />
      )}
      {activeTab === "prompt" && (
        <PromptPlayground flowId={flowId} onClose={onClose} embedded />
      )}
      {activeTab === "evals" && (
        <FlowEvalsPage
          flowId={flowId}
          onViewRun={onViewRun || (() => {})}
          onClose={onClose}
          embedded
        />
      )}
    </GroupModal>
  );
}
