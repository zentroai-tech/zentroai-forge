"use client";

import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { listFlowVersions, restoreFlowVersion, labelFlowVersion, getFlow } from "@/lib/api";
import type { FlowVersionItem } from "@/lib/api";
import { useFlowStore } from "@/lib/store";

interface FlowVersionHistoryProps {
  flowId: string;
  onClose: () => void;
  embedded?: boolean;
}

export default function FlowVersionHistory({ flowId, onClose, embedded }: FlowVersionHistoryProps) {
  const [versions, setVersions] = useState<FlowVersionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState<number | null>(null);
  const [labeling, setLabeling] = useState<number | null>(null);
  const [editLabel, setEditLabel] = useState<{ version_number: number; value: string } | null>(null);
  const { setCurrentFlow } = useFlowStore();

  const loadVersions = useCallback(async () => {
    if (!flowId) return;
    setLoading(true);
    try {
      const data = await listFlowVersions(flowId);
      setVersions(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load versions");
    } finally {
      setLoading(false);
    }
  }, [flowId]);

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  const handleRestore = async (versionNumber: number) => {
    if (!flowId) return;
    setRestoring(versionNumber);
    try {
      await restoreFlowVersion(flowId, versionNumber);
      const flow = await getFlow(flowId);
      setCurrentFlow(flow);
      toast.success(`Restored to version ${versionNumber}`);
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Restore failed");
    } finally {
      setRestoring(null);
    }
  };

  const handleSaveLabel = async (versionNumber: number, label: string) => {
    if (!flowId) return;
    setLabeling(versionNumber);
    try {
      const updated = await labelFlowVersion(flowId, versionNumber, label);
      setVersions((prev) =>
        prev.map((v) => (v.version_number === versionNumber ? { ...v, label: updated.label } : v))
      );
      setEditLabel(null);
      toast.success("Label updated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update label");
    } finally {
      setLabeling(null);
    }
  };

  const contentBody = (
    <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="w-6 h-6 border-2 border-[var(--border-default)] border-t-[var(--text-secondary)] rounded-full animate-spin" />
            </div>
          ) : versions.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)]">No versions yet. Versions are created when you save the flow.</p>
          ) : (
            <ul className="space-y-2">
              {versions.map((v) => (
                <li
                  key={v.id}
                  className="rounded-lg border p-3 flex items-center justify-between gap-2"
                  style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-primary)" }}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">v{v.version_number}</span>
                      {editLabel?.version_number === v.version_number ? (
                        <div className="flex gap-1 items-center">
                          <input
                            type="text"
                            value={editLabel.value}
                            onChange={(e) => setEditLabel((x) => (x ? { ...x, value: e.target.value } : null))}
                            className="input-field text-xs flex-1 min-w-0"
                            placeholder="Label"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveLabel(v.version_number, editLabel.value);
                              if (e.key === "Escape") setEditLabel(null);
                            }}
                          />
                          <button
                            onClick={() => handleSaveLabel(v.version_number, editLabel.value)}
                            disabled={labeling === v.version_number}
                            className="btn-pill !text-xs !px-2 !py-0.5"
                          >
                            {labeling === v.version_number ? "..." : "Save"}
                          </button>
                          <button onClick={() => setEditLabel(null)} className="text-xs text-[var(--text-muted)]">Cancel</button>
                        </div>
                      ) : (
                        <>
                          {v.label && <span className="text-xs text-[var(--text-muted)] truncate">{v.label}</span>}
                          <button
                            onClick={() => setEditLabel({ version_number: v.version_number, value: v.label })}
                            className="text-xs text-[var(--text-secondary)] hover:underline"
                          >
                            {v.label ? "Edit label" : "Add label"}
                          </button>
                        </>
                      )}
                    </div>
                    <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                      {new Date(v.created_at).toLocaleString()}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRestore(v.version_number)}
                    disabled={restoring !== null}
                    className="btn-pill shrink-0"
                  >
                    {restoring === v.version_number ? "Restoring..." : "Restore"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
  );

  if (embedded) return <div className="h-full flex flex-col">{contentBody}</div>;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col border"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="p-4 border-b flex items-center justify-between flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
          <h2 className="text-lg font-semibold text-white">Version History</h2>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--bg-tertiary)]" style={{ color: "var(--text-muted)" }}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {contentBody}
      </div>
    </div>
  );
}
