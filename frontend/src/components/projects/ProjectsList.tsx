"use client";

import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { listFlows, getFlow, deleteFlow } from "@/lib/api";
import { useFlowStore } from "@/lib/store";
import { formatDate } from "@/lib/utils";
import type { FlowListItem } from "@/types/ir";
import CreateProjectModal from "./CreateProjectModal";

interface ProjectsListProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ProjectsList({ isOpen, onClose }: ProjectsListProps) {
  const { currentFlow, setCurrentFlow, hasUnsavedChanges, createNewFlow } = useFlowStore();
  const [flows, setFlows] = useState<FlowListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const loadFlows = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listFlows();
      setFlows(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load projects");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadFlows();
    }
  }, [isOpen, loadFlows]);

  const handleSelectFlow = async (flowId: string) => {
    if (hasUnsavedChanges && !confirm("You have unsaved changes. Load anyway?")) {
      return;
    }

    setIsLoading(true);
    try {
      const flow = await getFlow(flowId);
      setCurrentFlow(flow);
      onClose();
      toast.success(`Loaded: ${flow.name}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load project");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateNew = () => {
    if (hasUnsavedChanges && !confirm("You have unsaved changes. Create new anyway?")) {
      return;
    }
    setShowCreateModal(true);
  };

  const handleProjectCreated = () => {
    setShowCreateModal(false);
    loadFlows();
    onClose();
  };

  const handleDeleteFlow = async (e: React.MouseEvent, flowId: string, flowName: string) => {
    e.stopPropagation(); // Prevent selecting the flow when clicking delete

    if (!confirm(`Delete project "${flowName}"? This cannot be undone.`)) {
      return;
    }

    setIsLoading(true);
    try {
      await deleteFlow(flowId);
      toast.success(`Deleted: ${flowName}`);

      // If the deleted flow was the current one, clear it
      if (currentFlow?.id === flowId) {
        createNewFlow("New Flow");
      }

      // Remove from local list
      setFlows((prev) => prev.filter((f) => f.id !== flowId));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete project");
    } finally {
      setIsLoading(false);
    }
  };

  const filteredFlows = flows.filter((flow) =>
    flow.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-start justify-center z-50 pt-20 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[70vh] flex flex-col border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Projects</h2>
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

        {/* Search & Actions */}
        <div
          className="p-4 border-b flex gap-3"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex-1 relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
              style={{ color: "var(--text-muted)" }}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              type="text"
              placeholder="Search projects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 rounded-lg focus:outline-none focus:border-[var(--border-active)]"
              style={{
                backgroundColor: "var(--bg-tertiary)",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
              }}
            />
          </div>
          <button
            onClick={loadFlows}
            disabled={isLoading}
            className="p-2 rounded-lg transition-colors hover:bg-[var(--bg-tertiary)]"
            style={{
              color: "var(--text-muted)",
              border: "1px solid var(--border-default)",
            }}
            title="Refresh"
          >
            <svg className={`w-5 h-5 ${isLoading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <button onClick={handleCreateNew} className="btn-pill">
            New Project
          </button>
        </div>

        {/* Projects List */}
        <div className="flex-1 overflow-y-auto p-4" style={{ backgroundColor: "var(--bg-primary)" }}>
          {isLoading && flows.length === 0 ? (
            <div className="text-center py-8">
              <p style={{ color: "var(--text-muted)" }}>Loading projects...</p>
            </div>
          ) : filteredFlows.length === 0 ? (
            <div className="text-center py-8">
              <div
                className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center"
                style={{ backgroundColor: "var(--bg-tertiary)" }}
              >
                <svg className="w-8 h-8" style={{ color: "var(--text-muted)" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
              </div>
              <p style={{ color: "var(--text-secondary)" }} className="mb-2">
                {searchQuery ? "No projects match your search" : "No projects yet"}
              </p>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {searchQuery ? "Try a different search term" : "Create your first project to get started"}
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              {filteredFlows.map((flow) => (
                <div
                  key={flow.id}
                  className="w-full text-left p-4 rounded-xl border-2 transition-all group"
                  style={{
                    backgroundColor: currentFlow?.id === flow.id
                      ? "rgba(139, 148, 158, 0.08)"
                      : "var(--bg-secondary)",
                    borderColor: currentFlow?.id === flow.id
                      ? "var(--border-active)"
                      : "var(--border-default)",
                  }}
                  onMouseEnter={(e) => {
                    if (currentFlow?.id !== flow.id) {
                      e.currentTarget.style.borderColor = "var(--text-muted)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (currentFlow?.id !== flow.id) {
                      e.currentTarget.style.borderColor = "var(--border-default)";
                    }
                  }}
                >
                  <div className="flex items-start justify-between">
                    <button
                      onClick={() => handleSelectFlow(flow.id)}
                      disabled={isLoading}
                      className="flex-1 min-w-0 text-left"
                    >
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-white truncate">{flow.name}</h3>
                        {currentFlow?.id === flow.id && (
                          <span
                            className="px-2 py-0.5 text-xs rounded-full"
                            style={{
                              backgroundColor: "var(--bg-tertiary)",
                              color: "var(--text-secondary)",
                            }}
                          >
                            Active
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                        <span>v{flow.version}</span>
                        {flow.created_at && (
                          <>
                            <span style={{ color: "var(--border-default)" }}>•</span>
                            <span>{formatDate(flow.created_at)}</span>
                          </>
                        )}
                      </div>
                    </button>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        onClick={(e) => handleDeleteFlow(e, flow.id, flow.name)}
                        disabled={isLoading}
                        className="p-1.5 rounded opacity-0 group-hover:opacity-100 transition-all hover:bg-red-500/20"
                        style={{ color: "var(--text-muted)" }}
                        onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-muted)"; }}
                        title="Delete project"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                      <svg
                        className="w-5 h-5"
                        style={{ color: "var(--text-muted)" }}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="p-4 border-t text-xs"
          style={{
            borderColor: "var(--border-default)",
            backgroundColor: "var(--bg-tertiary)",
            color: "var(--text-muted)",
          }}
        >
          {filteredFlows.length > 0 && (
            <span>{filteredFlows.length} project{filteredFlows.length !== 1 ? "s" : ""}</span>
          )}
        </div>
      </div>

      {/* Create Project Modal */}
      <CreateProjectModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onProjectCreated={handleProjectCreated}
      />
    </div>
  );
}
