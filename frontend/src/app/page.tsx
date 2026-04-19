"use client";

import { useState, useEffect } from "react";
import { FlowCanvas, FlowToolbar, NodePalette, NodeInspector } from "@/components/flow";
import { NavRail, FlowBrowser, BottomDock } from "@/components/layout";
import { SettingsModal } from "@/components/credentials";
import { useFlowStore } from "@/lib/store";

export default function Home() {
  const {
    currentFlow,
    hasUnsavedChanges,
    createNewFlow,
    bottomDockGroup,
    bottomDockTab,
    openBottomDock,
    closeBottomDock,
    setBottomDockTab,
  } = useFlowStore();

  const [navRailPanel, setNavRailPanel] = useState<"flows" | "settings" | null>(null);
  const [showNewRun, setShowNewRun] = useState(false);

  const [showSettings, setShowSettings] = useState(false);
  const [settingsScope, setSettingsScope] = useState<"workspace" | "project">("workspace");
  const [mounted, setMounted] = useState(false);

  // Handle hydration mismatch with persisted state
  useEffect(() => {
    setMounted(true);
  }, []);

  // Warn before leaving with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = "";
        return "";
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [hasUnsavedChanges]);

  // Create a new flow if none exists
  useEffect(() => {
    if (mounted && !currentFlow) {
      createNewFlow("My First Flow");
    }
  }, [mounted, currentFlow, createNewFlow]);

  const openGroup = (group: "run" | "test" | "code", tab?: string) => {
    openBottomDock(group, tab);
    if (group !== "run") setShowNewRun(false);
  };

  if (!mounted) {
    return (
      <div className="h-screen flex items-center justify-center" style={{ backgroundColor: "var(--bg-primary)" }}>
        <p style={{ color: "var(--text-muted)" }}>Loading...</p>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col" style={{ backgroundColor: "var(--bg-primary)" }}>
      <FlowToolbar
        onOpenGroup={openGroup}
        onRunFlow={() => {
          setShowNewRun(true);
          openBottomDock("run", "runs");
        }}
      />

      <div className="flex-1 flex overflow-hidden relative">
        <NavRail activePanel={navRailPanel} onSetPanel={setNavRailPanel} />
        <FlowBrowser
          isOpen={navRailPanel === "flows"}
          onClose={() => setNavRailPanel(null)}
        />
        <NodePalette disabled={!currentFlow} hidden={navRailPanel === "flows"} />
        <FlowCanvas />
        <NodeInspector />
      </div>

      <BottomDock
        activeGroup={bottomDockGroup}
        activeTab={bottomDockTab}
        flowId={currentFlow?.id ?? ""}
        initialShowNewRun={showNewRun}
        onClose={closeBottomDock}
        onTabChange={setBottomDockTab}
        onOpenSettings={(scope) => {
          setSettingsScope(scope);
          setShowSettings(true);
        }}
        onViewRun={() => openBottomDock("run", "runs")}
      />

      <SettingsModal
        isOpen={showSettings || navRailPanel === "settings"}
        onClose={() => {
          setShowSettings(false);
          if (navRailPanel === "settings") setNavRailPanel(null);
        }}
        scope={settingsScope}
        projectId={currentFlow?.id}
      />
    </div>
  );
}
