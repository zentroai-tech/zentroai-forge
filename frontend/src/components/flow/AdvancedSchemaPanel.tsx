"use client";

import { useEffect, useMemo, useState } from "react";
import type { HandoffRule } from "@/types/agents";

interface AdvancedSchemaPanelProps {
  isOpen: boolean;
  onClose: () => void;
  handoffs: HandoffRule[];
  schemaContracts: Record<string, Record<string, unknown>>;
  onOpenSchemaManager: () => void;
  onSave: (handoffs: HandoffRule[]) => void;
}

const NONE_VALUE = "__none__";

export default function AdvancedSchemaPanel({
  isOpen,
  onClose,
  handoffs,
  schemaContracts,
  onOpenSchemaManager,
  onSave,
}: AdvancedSchemaPanelProps) {
  const [draft, setDraft] = useState<HandoffRule[]>(handoffs);

  useEffect(() => {
    setDraft(handoffs);
  }, [handoffs, isOpen]);

  const schemaIds = useMemo(() => Object.keys(schemaContracts).sort(), [schemaContracts]);

  if (!isOpen) return null;

  const getSchemaIdFromRef = (ref?: string | null): string =>
    ref && ref.startsWith("schema://") ? ref.replace("schema://", "") : NONE_VALUE;

  const applySchemaRef = (
    list: HandoffRule[],
    index: number,
    field: "input_schema" | "output_schema",
    selectedSchemaId: string
  ): HandoffRule[] => {
    return list.map((item, i) => {
      if (i !== index) return item;
      if (selectedSchemaId === NONE_VALUE) {
        return { ...item, [field]: null };
      }
      return {
        ...item,
        [field]: {
          kind: "json_schema",
          ref: `schema://${selectedSchemaId}`,
        },
      };
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div
        className="w-full max-w-4xl overflow-hidden rounded-xl border shadow-2xl"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
              Schema Contracts (Handoffs)
            </h2>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              Select schemas managed in Schema Manager
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onOpenSchemaManager} className="btn-secondary text-xs">Schema Manager</button>
            <button onClick={onClose} className="btn-secondary text-xs">Close</button>
          </div>
        </div>

        <div className="space-y-3 p-4">
          {draft.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>No handoffs available. Create handoffs first.</p>
          ) : (
            <div className="max-h-[60vh] space-y-3 overflow-auto">
              {draft.map((handoff, index) => (
                <div
                  key={`${handoff.from_agent_id}-${handoff.to_agent_id}-${index}`}
                  className="rounded-lg border p-3"
                  style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}
                >
                  <div className="mb-2 text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                    {handoff.from_agent_id} -&gt; {handoff.to_agent_id} <span style={{ color: "var(--text-muted)" }}>({handoff.mode})</span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
                      Input schema
                      <select
                        value={getSchemaIdFromRef(handoff.input_schema?.ref)}
                        onChange={(e) => setDraft((prev) => applySchemaRef(prev, index, "input_schema", e.target.value))}
                        className="input-field mt-1 text-xs"
                      >
                        <option value={NONE_VALUE}>None</option>
                        {schemaIds.map((schemaId) => (
                          <option key={schemaId} value={schemaId}>{schemaId}</option>
                        ))}
                      </select>
                    </label>
                    <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
                      Output schema
                      <select
                        value={getSchemaIdFromRef(handoff.output_schema?.ref)}
                        onChange={(e) => setDraft((prev) => applySchemaRef(prev, index, "output_schema", e.target.value))}
                        className="input-field mt-1 text-xs"
                      >
                        <option value={NONE_VALUE}>None</option>
                        {schemaIds.map((schemaId) => (
                          <option key={schemaId} value={schemaId}>{schemaId}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {schemaIds.length === 0 && (
                    <p className="mt-2 text-[11px]" style={{ color: "var(--warning)" }}>
                      No schemas defined. Open Schema Manager to create contracts.
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="btn-secondary text-xs">Cancel</button>
            <button onClick={() => onSave(draft)} className="btn-pill active text-xs">
              Save Schemas
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

