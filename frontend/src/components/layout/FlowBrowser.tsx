"use client";

import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { listFlows, getFlow, updateFlow, deleteFlow } from "@/lib/api";
import { useFlowStore } from "@/lib/store";
import type { FlowListItem } from "@/types/ir";
import CreateProjectModal from "@/components/projects/CreateProjectModal";

interface FlowBrowserProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function FlowBrowser({ isOpen, onClose }: FlowBrowserProps) {
  const { currentFlow, setCurrentFlow, hasUnsavedChanges } = useFlowStore();
  const [flows, setFlows] = useState<FlowListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingFlowId, setEditingFlowId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  const loadFlows = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listFlows();
      setFlows(data);
    } catch {
      // Silently ignore if backend is unreachable
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) loadFlows();
  }, [isOpen, loadFlows]);

  const startRename = (flow: FlowListItem) => {
    setEditingFlowId(flow.id);
    setEditingName(flow.name);
  };

  const cancelRename = () => {
    setEditingFlowId(null);
    setEditingName("");
  };

  const handleLoad = async (flowId: string) => {
    if (hasUnsavedChanges && !confirm("You have unsaved changes. Load anyway?")) return;
    setIsLoading(true);
    try {
      const flow = await getFlow(flowId);
      setCurrentFlow(flow);
      onClose();
      toast.success(`Loaded: ${flow.name}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load flow");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRename = async (flowId: string) => {
    const nextName = editingName.trim();
    if (!nextName) {
      toast.error("Project name is required");
      return;
    }

    if (currentFlow?.id === flowId && hasUnsavedChanges) {
      toast.error("Save or discard the current project changes before renaming it.");
      return;
    }

    setIsLoading(true);
    try {
      const flow = await getFlow(flowId);
      const updated = await updateFlow(flowId, {
        ...flow,
        name: nextName,
      });

      setFlows((prev) =>
        prev.map((item) =>
          item.id === flowId
            ? {
                ...item,
                name: updated.name,
                updated_at: updated.updated_at || item.updated_at,
              }
            : item
        )
      );

      if (currentFlow?.id === flowId) {
        setCurrentFlow(updated);
      }

      cancelRename();
      toast.success(`Renamed: ${updated.name}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to rename project");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (flowId: string, flowName: string) => {
    const deletingActive = currentFlow?.id === flowId;
    const message = deletingActive && hasUnsavedChanges
      ? `Delete project "${flowName}"? Unsaved changes in the current editor will be lost.`
      : `Delete project "${flowName}"? This cannot be undone.`;

    if (!confirm(message)) return;

    setIsLoading(true);
    try {
      await deleteFlow(flowId);
      setFlows((prev) => prev.filter((flow) => flow.id !== flowId));

      if (deletingActive) {
        setCurrentFlow(null);
      }

      if (editingFlowId === flowId) {
        cancelRename();
      }

      toast.success(`Deleted: ${flowName}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete project");
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewFlow = () => {
    if (hasUnsavedChanges && !confirm("You have unsaved changes. Create new anyway?")) return;
    setShowCreateModal(true);
  };

  if (!isOpen) return null;

  const filtered = flows.filter((f) =>
    f.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div
      className="w-60 flex flex-col border-r flex-shrink-0 z-20"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-default)",
      }}
    >
      {/* Header */}
      <div
        className="h-10 flex items-center justify-between px-3 border-b flex-shrink-0"
        style={{ borderColor: "var(--border-default)" }}
      >
        <span className="text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
          Flows
        </span>
        <button
          onClick={handleNewFlow}
          className="w-6 h-6 flex items-center justify-center rounded text-lg leading-none transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-muted)" }}
          title="New flow"
        >
          +
        </button>
      </div>

      {/* Search */}
      <div className="px-2 py-2 border-b flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search flows..."
          className="input-field w-full text-xs"
        />
      </div>

      {/* Flow list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && flows.length === 0 ? (
          <p className="text-xs text-center py-6" style={{ color: "var(--text-muted)" }}>
            Loading...
          </p>
        ) : filtered.length === 0 ? (
          <div className="px-3 py-6 text-center">
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              {searchQuery ? "No flows match" : "No saved flows"}
            </p>
            {!searchQuery && (
              <button
                onClick={handleNewFlow}
                className="mt-2 text-xs underline"
                style={{ color: "var(--accent-primary)" }}
              >
                Create first flow
              </button>
            )}
          </div>
        ) : (
          filtered.map((flow) => {
            const isActive = currentFlow?.id === flow.id;
            const isEditing = editingFlowId === flow.id;
            return (
              <div
                key={flow.id}
                className="group flex items-center justify-between px-3 py-2 transition-colors hover:bg-[var(--bg-tertiary)]"
                style={{
                  backgroundColor: isActive ? "var(--bg-selected)" : "transparent",
                }}
              >
                <span
                  className="text-xs truncate flex-1 mr-2"
                  style={{
                    color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                  fontWeight: isActive ? 500 : 400,
                  }}
                  title={flow.name}
                >
                  {isEditing ? (
                    <input
                      type="text"
                      value={editingName}
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void handleRename(flow.id);
                        }
                        if (e.key === "Escape") {
                          e.preventDefault();
                          cancelRename();
                        }
                      }}
                      className="input-field w-full text-xs"
                    />
                  ) : (
                    flow.name
                  )}
                </span>
                {isEditing ? (
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => void handleRename(flow.id)}
                      disabled={isLoading}
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Save
                    </button>
                    <button
                      onClick={cancelRename}
                      disabled={isLoading}
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "var(--text-muted)",
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : isActive ? (
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "var(--text-muted)",
                      }}
                    >
                      active
                    </span>
                    <button
                      onClick={() => startRename(flow)}
                      disabled={isLoading}
                      className="text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "var(--text-secondary)",
                      }}
                      title="Rename project"
                    >
                      Rename
                    </button>
                    <button
                      onClick={() => void handleDelete(flow.id, flow.name)}
                      disabled={isLoading}
                      className="text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "#f87171",
                      }}
                      title="Delete project"
                    >
                      Delete
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => handleLoad(flow.id)}
                      disabled={isLoading}
                      className="text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Load
                    </button>
                    <button
                      onClick={() => startRename(flow)}
                      disabled={isLoading}
                      className="text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "var(--text-secondary)",
                      }}
                      title="Rename project"
                    >
                      Rename
                    </button>
                    <button
                      onClick={() => void handleDelete(flow.id, flow.name)}
                      disabled={isLoading}
                      className="text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: "#f87171",
                      }}
                      title="Delete project"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <CreateProjectModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onProjectCreated={() => {
          setShowCreateModal(false);
          loadFlows();
        }}
      />
    </div>
  );
}
