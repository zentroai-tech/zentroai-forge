"use client";

import { useEffect, useState } from "react";
import type { PolicySpec } from "@/types/agents";

interface AdvancedPolicyPanelProps {
  isOpen: boolean;
  onClose: () => void;
  policy: PolicySpec;
  onSave: (policy: PolicySpec) => void;
}

function csvToList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function AdvancedPolicyPanel({ isOpen, onClose, policy, onSave }: AdvancedPolicyPanelProps) {
  const [draft, setDraft] = useState<PolicySpec>(policy);
  const [allowCsv, setAllowCsv] = useState("");
  const [denyCsv, setDenyCsv] = useState("");
  const [patternsCsv, setPatternsCsv] = useState("");

  useEffect(() => {
    setDraft(policy);
    setAllowCsv((policy.tool_allowlist || []).join(", "));
    setDenyCsv((policy.tool_denylist || []).join(", "));
    setPatternsCsv((policy.redaction?.patterns || []).join(", "));
  }, [policy, isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div
        className="w-full max-w-3xl overflow-hidden rounded-xl border shadow-2xl"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
              Advanced Policies
            </h2>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              Global guardrails, sanitization and redaction
            </p>
          </div>
          <button onClick={onClose} className="btn-secondary text-xs">Close</button>
        </div>

        <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <label className="col-span-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            Tool allowlist (CSV)
            <input value={allowCsv} onChange={(e) => setAllowCsv(e.target.value)} className="input-field mt-1 text-xs" />
          </label>
          <label className="col-span-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            Tool denylist (CSV)
            <input value={denyCsv} onChange={(e) => setDenyCsv(e.target.value)} className="input-field mt-1 text-xs" />
          </label>
          <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Max tool calls
            <input type="number" value={draft.max_tool_calls ?? ""} onChange={(e) => setDraft((p) => ({ ...p, max_tool_calls: e.target.value ? Number(e.target.value) : null }))} className="input-field mt-1 text-xs" />
          </label>
          <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Max steps
            <input type="number" value={draft.max_steps ?? ""} onChange={(e) => setDraft((p) => ({ ...p, max_steps: e.target.value ? Number(e.target.value) : null }))} className="input-field mt-1 text-xs" />
          </label>
          <label className="col-span-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            Redaction patterns (CSV regex)
            <input value={patternsCsv} onChange={(e) => setPatternsCsv(e.target.value)} className="input-field mt-1 text-xs" />
          </label>
          <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Redaction mask
            <input value={draft.redaction.mask} onChange={(e) => setDraft((p) => ({ ...p, redaction: { ...p.redaction, mask: e.target.value } }))} className="input-field mt-1 text-xs" />
          </label>
          <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Input max chars
            <input type="number" value={draft.input_sanitization.max_input_chars} onChange={(e) => setDraft((p) => ({ ...p, input_sanitization: { ...p.input_sanitization, max_input_chars: Math.max(1, Number(e.target.value || 1)) } }))} className="input-field mt-1 text-xs" />
          </label>

          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={draft.allow_schema_soft_fail} onChange={(e) => setDraft((p) => ({ ...p, allow_schema_soft_fail: e.target.checked }))} />
            Allow schema soft-fail
          </label>
          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={draft.redaction.enabled} onChange={(e) => setDraft((p) => ({ ...p, redaction: { ...p.redaction, enabled: e.target.checked } }))} />
            Enable redaction
          </label>
          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={draft.input_sanitization.enabled} onChange={(e) => setDraft((p) => ({ ...p, input_sanitization: { ...p.input_sanitization, enabled: e.target.checked } }))} />
            Enable input sanitization
          </label>
          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={draft.input_sanitization.strip_html} onChange={(e) => setDraft((p) => ({ ...p, input_sanitization: { ...p.input_sanitization, strip_html: e.target.checked } }))} />
            Strip HTML
          </label>
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary text-xs">Cancel</button>
          <button
            onClick={() =>
              onSave({
                ...draft,
                tool_allowlist: csvToList(allowCsv),
                tool_denylist: csvToList(denyCsv),
                redaction: {
                  ...draft.redaction,
                  patterns: csvToList(patternsCsv),
                },
              })
            }
            className="btn-pill active text-xs"
          >
            Save Policy
          </button>
        </div>
        </div>
      </div>
    </div>
  );
}
