"use client";

import { useMemo } from "react";
import { useModels } from "@/hooks/useModels";
import type { ModelProvider } from "@/types/models";
import { RECOMMENDED_MODELS } from "@/types/models";

interface ModelSelectProps {
  provider: ModelProvider | "auto";
  value: string;
  projectId: string;
  region?: string | null;
  onChange: (modelId: string) => void;
}

/**
 * Model selector dropdown with registry integration.
 *
 * Shows:
 * - Recommended models section (static, always visible)
 * - All models section from registry (fetched + cached)
 * - Refresh button
 * - Stale data indicator
 */
export default function ModelSelect({
  provider,
  value,
  projectId,
  region,
  onChange,
}: ModelSelectProps) {
  const { models, loading, error, warning, lastUpdated, refresh } = useModels(
    provider,
    projectId,
    region
  );

  const recommended = useMemo(() => {
    if (provider === "auto") return [];
    return RECOMMENDED_MODELS[provider] || [];
  }, [provider]);

  const allModelIds = useMemo(() => new Set(models.map((m) => m.id)), [models]);

  // If registry loaded, separate recommended from rest
  const recommendedModels = useMemo(
    () => models.filter((m) => recommended.includes(m.id)),
    [models, recommended]
  );
  const otherModels = useMemo(
    () => models.filter((m) => !recommended.includes(m.id)),
    [models, recommended]
  );

  const formatTime = (iso: string | null) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffH = Math.floor(diffMs / 3_600_000);
      if (diffH < 1) return "just now";
      if (diffH < 24) return `${diffH}h ago`;
      const diffD = Math.floor(diffH / 24);
      return `${diffD}d ago`;
    } catch {
      return null;
    }
  };

  // If provider is auto or no project, fall back to a simple text input
  if (provider === "auto" || !projectId) {
    return (
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input-field"
        placeholder="e.g., gpt-4o, claude-sonnet-4-5-20250929, gemini-2.0-flash"
      />
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="input-field flex-1"
        >
          {/* Current value always shown (even if not in list yet) */}
          {value && !allModelIds.has(value) && models.length > 0 && (
            <option value={value}>{value} (custom)</option>
          )}

          {/* Recommended section */}
          {recommendedModels.length > 0 && (
            <optgroup label="Recommended">
              {recommendedModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </optgroup>
          )}

          {/* Show static recommended if registry hasn't loaded yet */}
          {models.length === 0 && recommended.length > 0 && (
            <optgroup label="Recommended">
              {recommended.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </optgroup>
          )}

          {/* All models section */}
          {otherModels.length > 0 && (
            <optgroup label="All models">
              {otherModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </optgroup>
          )}
        </select>

        {/* Refresh button */}
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            refresh();
          }}
          disabled={loading}
          className="p-1.5 rounded hover:bg-[var(--bg-tertiary)] text-[var(--text-muted)] hover:text-white transition-colors disabled:opacity-50"
          title="Refresh models"
        >
          <svg
            className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      {/* Status line */}
      <div className="flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
        {loading && <span>Loading models...</span>}
        {error && <span className="text-red-400">{error}</span>}
        {warning && (
          <span className="text-yellow-400">Using cached data (provider unavailable)</span>
        )}
        {!loading && !error && lastUpdated && (
          <span>Updated {formatTime(lastUpdated)}</span>
        )}
      </div>
    </div>
  );
}
