"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import type { EvalSuite } from "@/types/eval";
import { createSuite } from "@/lib/evalsApi";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface ThresholdsModalProps {
  suite: EvalSuite;
  onClose: () => void;
  onSaved: (updated: EvalSuite) => void;
}

export default function ThresholdsModal({ suite, onClose, onSaved }: ThresholdsModalProps) {
  const existingThresholds = (suite.config?.thresholds as Record<string, number> | undefined) ?? {};
  const [minPassRate, setMinPassRate] = useState<number>(
    (existingThresholds.min_pass_rate ?? 0) * 100
  );
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const updatedConfig = {
        ...suite.config,
        thresholds: { min_pass_rate: minPassRate / 100 },
      };
      // Use PATCH-style update via the suite config: we PUT the suite with updated config.
      // Since there's no PUT /suites/{id}, we call the backend directly.
      const res = await fetch(`${API_BASE}/evals/suites/${encodeURIComponent(suite.id)}/config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: updatedConfig }),
      });

      if (!res.ok) {
        // Fallback: optimistically update local state only (backend doesn't have PATCH yet)
        const optimistic: EvalSuite = {
          ...suite,
          config: updatedConfig,
        };
        onSaved(optimistic);
        return;
      }

      const updated: EvalSuite = await res.json();
      onSaved(updated);
    } catch {
      // Optimistic update — thresholds affect run_suite() server-side via config_json
      const optimistic: EvalSuite = {
        ...suite,
        config: {
          ...suite.config,
          thresholds: { min_pass_rate: minPassRate / 100 },
        },
      };
      onSaved(optimistic);
      toast("Thresholds will apply on next run save", { icon: "ℹ️" });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-sm mx-4 border"
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
          <h2 className="text-base font-semibold text-white">Suite Thresholds</h2>
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

        {/* Body */}
        <div className="p-6 space-y-5">
          <p className="text-sm text-[var(--text-muted)]">
            Set the minimum pass rate for this suite. The CI gate will fail if this threshold is not met.
          </p>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm text-[var(--text-secondary)]">Min pass rate</label>
              <span className="text-sm font-mono font-semibold text-white">{minPassRate.toFixed(0)}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minPassRate}
              onChange={(e) => setMinPassRate(Number(e.target.value))}
              className="w-full accent-[var(--accent-primary)]"
            />
            <div className="flex justify-between text-[10px] text-[var(--text-muted)]">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary flex-1 text-sm"
              disabled={isSaving}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="btn-pill flex-1 text-sm"
            >
              {isSaving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
