"use client";

import { useEffect, useMemo, useRef, useState } from "react";

interface SchemaManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  schemas: Record<string, Record<string, unknown>>;
  onSave: (schemas: Record<string, Record<string, unknown>>) => void;
}

const EMPTY_SCHEMA = `{
  "type": "object",
  "properties": {},
  "required": []
}`;

export default function SchemaManagerModal({ isOpen, onClose, schemas, onSave }: SchemaManagerModalProps) {
  const [draft, setDraft] = useState<Record<string, Record<string, unknown>>>({});
  const [selectedId, setSelectedId] = useState<string>("");
  const [newId, setNewId] = useState("");
  const [editorValue, setEditorValue] = useState(EMPTY_SCHEMA);
  const [error, setError] = useState<string | null>(null);
  const [hasPendingChanges, setHasPendingChanges] = useState(false);
  const wasOpenRef = useRef(false);

  const ids = useMemo(() => Object.keys(draft).sort(), [draft]);

  useEffect(() => {
    // Hydrate only on open transition to avoid overwriting in-progress edits.
    if (isOpen && !wasOpenRef.current) {
      setDraft(schemas || {});
      const first = Object.keys(schemas || {})[0] || "";
      setSelectedId(first);
      setEditorValue(first ? JSON.stringify((schemas || {})[first], null, 2) : EMPTY_SCHEMA);
      setError(null);
      setNewId("");
      setHasPendingChanges(false);
    }
    wasOpenRef.current = isOpen;
  }, [isOpen, schemas]);

  if (!isOpen) return null;

  const schemaIdRegex = /^[a-z][a-z0-9_\-]*$/;

  const getDraftWithEditorApplied = (): Record<string, Record<string, unknown>> | null => {
    if (!selectedId) return draft;
    try {
      const parsed = JSON.parse(editorValue);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError("Schema must be a JSON object.");
        return null;
      }
      const prevSerialized = JSON.stringify(draft[selectedId] || {});
      const nextSerialized = JSON.stringify(parsed);
      const next = { ...draft, [selectedId]: parsed as Record<string, unknown> };
      setDraft(next);
      if (prevSerialized !== nextSerialized) {
        setHasPendingChanges(true);
      }
      setError(null);
      return next;
    } catch {
      setError("Invalid JSON format.");
      return null;
    }
  };

  const handleSelect = (id: string) => {
    const next = getDraftWithEditorApplied();
    if (!next) return;
    setSelectedId(id);
    setEditorValue(JSON.stringify(next[id], null, 2));
    setError(null);
  };

  const handleCreate = () => {
    const id = newId.trim();
    if (!schemaIdRegex.test(id)) {
      setError("Schema ID must match: ^[a-z][a-z0-9_-]*$");
      return;
    }
    if (draft[id]) {
      setError("Schema ID already exists.");
      return;
    }
    const nextWithCurrent = getDraftWithEditorApplied();
    if (!nextWithCurrent) return;
    const parsed = JSON.parse(EMPTY_SCHEMA) as Record<string, unknown>;
    const next = { ...nextWithCurrent, [id]: parsed };
    setDraft(next);
    setSelectedId(id);
    setEditorValue(JSON.stringify(parsed, null, 2));
    setNewId("");
    setHasPendingChanges(true);
    setError(null);
  };

  const handleDelete = () => {
    if (!selectedId) return;
    const { [selectedId]: _, ...rest } = draft;
    const nextIds = Object.keys(rest).sort();
    setDraft(rest);
    setSelectedId(nextIds[0] || "");
    setEditorValue(nextIds[0] ? JSON.stringify(rest[nextIds[0]], null, 2) : EMPTY_SCHEMA);
    setHasPendingChanges(true);
    setError(null);
  };

  const handleApply = (): boolean => {
    const next = getDraftWithEditorApplied();
    if (!next) return false;
    onSave(next);
    setHasPendingChanges(false);
    return true;
  };

  const handleApplyAndClose = () => {
    const ok = handleApply();
    if (!ok) return;
    onClose();
  };

  const handleCloseWithConfirm = () => {
    if (hasPendingChanges) {
      const confirmClose = window.confirm("You have unapplied schema changes. Close without applying?");
      if (!confirmClose) return;
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div
        className="w-full max-w-5xl overflow-hidden rounded-xl border shadow-2xl"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
              Schema Manager
            </h2>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              Create and manage JSON Schemas used by handoff contracts
            </p>
          </div>
          <button onClick={handleCloseWithConfirm} className="btn-secondary text-xs">Close</button>
        </div>

        <div className="grid grid-cols-[260px_1fr] gap-4 p-4">
          <div className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}>
            <div className="mb-2 text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>Schemas</div>
            <div className="space-y-1 max-h-[52vh] overflow-auto">
              {ids.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleSelect(id)}
                  className="w-full rounded-md px-2 py-1.5 text-left text-xs transition-colors"
                  style={{
                    backgroundColor: id === selectedId ? "var(--bg-selected)" : "transparent",
                    color: id === selectedId ? "var(--text-primary)" : "var(--text-secondary)",
                    border: `1px solid ${id === selectedId ? "var(--border-active)" : "transparent"}`,
                  }}
                >
                  {id}
                </button>
              ))}
              {ids.length === 0 && (
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>No schemas yet.</p>
              )}
            </div>

            <div className="mt-3 space-y-2">
              <input
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="new schema id"
                className="input-field text-xs"
              />
              <div className="flex gap-2">
                <button onClick={handleCreate} className="btn-secondary text-xs">Add</button>
                <button onClick={handleDelete} className="btn-secondary text-xs" disabled={!selectedId}>Delete</button>
              </div>
            </div>
          </div>

          <div className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}>
            <div className="mb-2 text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
              {selectedId ? `schema://${selectedId}` : "Schema JSON"}
            </div>
            <textarea
              value={editorValue}
              onChange={(e) => {
                setEditorValue(e.target.value);
                setHasPendingChanges(true);
              }}
              className="input-field h-[52vh] w-full font-mono text-xs"
              spellCheck={false}
            />
            {error && (
              <p className="mt-2 text-xs" style={{ color: "var(--error)" }}>{error}</p>
            )}
            {!error && hasPendingChanges && (
              <p className="mt-2 text-xs" style={{ color: "var(--warning)" }}>
                Pending changes. Click Apply to update this flow.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <button onClick={handleCloseWithConfirm} className="btn-secondary text-xs">Cancel</button>
          <button onClick={handleApply} className="btn-secondary text-xs">Apply to Flow</button>
          <button onClick={handleApplyAndClose} className="btn-pill active text-xs">Apply + Close</button>
        </div>
      </div>
    </div>
  );
}
