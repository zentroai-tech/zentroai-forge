"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import toast from "react-hot-toast";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface EnvVar {
  id: string;
  key: string;
  value: string;
  profile: string;
  is_secret: boolean;
  created_at: string;
}

interface EnvManagerProps {
  flowId: string | undefined;
}

export default function EnvManager({ flowId }: EnvManagerProps) {
  const [profiles, setProfiles] = useState<string[]>(["development", "staging", "production"]);
  const [activeProfile, setActiveProfile] = useState("development");
  const [envVars, setEnvVars] = useState<EnvVar[]>([]);
  const [loading, setLoading] = useState(false);

  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newIsSecret, setNewIsSecret] = useState(false);
  const [adding, setAdding] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editIsSecret, setEditIsSecret] = useState(false);
  const [saving, setSaving] = useState(false);

  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set());
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const fetchProfiles = useCallback(async () => {
    if (!flowId) return;
    try {
      const res = await fetch(`${API}/flows/${flowId}/env/profiles`);
      if (res.ok) {
        const data = await res.json();
        setProfiles(data);
      }
    } catch {
      // ignore
    }
  }, [flowId]);

  const fetchVars = useCallback(async () => {
    if (!flowId) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    try {
      const res = await fetch(
        `${API}/flows/${flowId}/env?profile=${encodeURIComponent(activeProfile)}`,
        { signal: ctrl.signal }
      );
      if (res.ok) {
        const data = await res.json();
        setEnvVars(data);
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
    } finally {
      setLoading(false);
    }
  }, [flowId, activeProfile]);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  useEffect(() => {
    fetchVars();
    return () => abortRef.current?.abort();
  }, [fetchVars]);

  const handleAdd = async () => {
    if (!flowId) return;
    const trimmedKey = newKey.trim();
    if (!trimmedKey) {
      toast.error("Variable name is required");
      return;
    }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(trimmedKey)) {
      toast.error("Variable name must be alphanumeric with underscores");
      return;
    }
    setAdding(true);
    try {
      const res = await fetch(`${API}/flows/${flowId}/env`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: trimmedKey,
          value: newValue,
          profile: activeProfile,
          is_secret: newIsSecret,
        }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || "Failed to create variable");
      }
      toast.success(`Variable ${trimmedKey} saved`);
      setNewKey("");
      setNewValue("");
      setNewIsSecret(false);
      await fetchVars();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to add variable");
    } finally {
      setAdding(false);
    }
  };

  const handleUpdate = async (envVar: EnvVar) => {
    if (!flowId) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/flows/${flowId}/env`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: envVar.key,
          value: editValue,
          profile: activeProfile,
          is_secret: editIsSecret,
        }),
      });
      if (!res.ok) throw new Error("Failed to update variable");
      toast.success(`Updated ${envVar.key}`);
      setEditingId(null);
      await fetchVars();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (envVar: EnvVar) => {
    if (!flowId) return;
    try {
      const res = await fetch(`${API}/flows/${flowId}/env/${envVar.id}`, { method: "DELETE" });
      if (!res.ok && res.status !== 204) throw new Error("Failed to delete");
      toast.success(`Deleted ${envVar.key}`);
      setConfirmDeleteId(null);
      await fetchVars();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  const toggleReveal = (id: string) => {
    setRevealedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (!flowId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Save a flow first to manage environment variables.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-white">Environment Variables</h3>
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          Define per-profile variables for flow execution. Secret values are masked in the UI.
        </p>
      </div>

      <div className="flex items-center gap-1">
        {profiles.map((profile) => (
          <button
            key={profile}
            onClick={() => setActiveProfile(profile)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeProfile === profile
                ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-active)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] border border-transparent"
            }`}
          >
            {profile.charAt(0).toUpperCase() + profile.slice(1)}
          </button>
        ))}
      </div>

      <div
        className="rounded-lg border p-4 space-y-3"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Add Variable</span>
        <div className="flex gap-2 items-start">
          <div className="flex-1">
            <input
              type="text"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value.toUpperCase())}
              placeholder="VARIABLE_NAME"
              className="input-field w-full text-xs font-mono"
            />
          </div>
          <div className="flex-[2]">
            <input
              type={newIsSecret ? "password" : "text"}
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="value"
              className="input-field w-full text-xs"
            />
          </div>
          <label className="flex items-center gap-1.5 text-xs whitespace-nowrap pt-2" style={{ color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={newIsSecret} onChange={(e) => setNewIsSecret(e.target.checked)} className="rounded" />
            Secret
          </label>
          <button onClick={handleAdd} disabled={adding || !newKey.trim()} className="btn-pill text-xs px-3 py-2">
            {adding ? "..." : "Add"}
          </button>
        </div>
      </div>

      <div
        className="rounded-lg border overflow-hidden"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div
          className="grid grid-cols-[1fr_2fr_auto_auto] gap-2 px-4 py-2 text-xs font-medium border-b"
          style={{
            color: "var(--text-muted)",
            borderColor: "var(--border-default)",
            backgroundColor: "var(--bg-tertiary)",
          }}
        >
          <span>Name</span>
          <span>Value</span>
          <span>Type</span>
          <span>Actions</span>
        </div>

        {loading ? (
          <div className="px-4 py-8 text-center">
            <div className="inline-block w-5 h-5 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
          </div>
        ) : envVars.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
            No variables defined for <strong>{activeProfile}</strong> profile.
          </div>
        ) : (
          envVars.map((v) => (
            <div
              key={v.id}
              className="grid grid-cols-[1fr_2fr_auto_auto] gap-2 px-4 py-2.5 items-center border-b last:border-b-0"
              style={{ borderColor: "var(--border-default)" }}
            >
              <span className="text-xs font-mono font-medium text-[var(--text-primary)] truncate" title={v.key}>
                {v.key}
              </span>

              {editingId === v.id ? (
                <div className="flex gap-1 items-center">
                  <input
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    className="input-field text-xs flex-1"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleUpdate(v);
                      if (e.key === "Escape") setEditingId(null);
                    }}
                  />
                  <label className="flex items-center gap-1 text-xs whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                    <input type="checkbox" checked={editIsSecret} onChange={(e) => setEditIsSecret(e.target.checked)} className="rounded" />
                    Secret
                  </label>
                  <button onClick={() => handleUpdate(v)} disabled={saving} className="btn-pill !text-xs !px-2 !py-1">
                    {saving ? "..." : "Save"}
                  </button>
                  <button onClick={() => setEditingId(null)} className="text-xs px-2 py-1 rounded hover:bg-[var(--bg-tertiary)]" style={{ color: "var(--text-muted)" }}>
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <span className="text-xs truncate" style={{ color: "var(--text-secondary)" }}>
                    {v.is_secret && !revealedIds.has(v.id) ? "••••••••" : v.value}
                  </span>
                  {v.is_secret && (
                    <button onClick={() => toggleReveal(v.id)} className="p-0.5 rounded hover:bg-[var(--bg-tertiary)]" title={revealedIds.has(v.id) ? "Hide" : "Reveal"}>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: "var(--text-muted)" }}>
                        {revealedIds.has(v.id) ? (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                        ) : (
                          <>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </>
                        )}
                      </svg>
                    </button>
                  )}
                </div>
              )}

              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${v.is_secret ? "bg-amber-500/15 text-amber-400" : "bg-emerald-500/15 text-emerald-400"}`}>
                {v.is_secret ? "secret" : "plain"}
              </span>

              <div className="flex items-center gap-1">
                {editingId !== v.id && (
                  <button
                    onClick={() => {
                      setEditingId(v.id);
                      setEditValue(v.is_secret ? "" : v.value);
                      setEditIsSecret(v.is_secret);
                    }}
                    className="p-1 rounded hover:bg-[var(--bg-tertiary)]"
                    title="Edit"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: "var(--text-muted)" }}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                  </button>
                )}

                {confirmDeleteId === v.id ? (
                  <div className="flex items-center gap-1">
                    <button onClick={() => handleDelete(v)} className="text-[10px] px-2 py-0.5 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30">Confirm</button>
                    <button onClick={() => setConfirmDeleteId(null)} className="text-[10px] px-2 py-0.5 rounded hover:bg-[var(--bg-tertiary)]" style={{ color: "var(--text-muted)" }}>No</button>
                  </div>
                ) : (
                  <button onClick={() => setConfirmDeleteId(v.id)} className="p-1 rounded hover:bg-red-500/10" title="Delete">
                    <svg className="w-3.5 h-3.5 text-red-400/60 hover:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <div
        className="rounded-lg border p-3 text-xs space-y-2"
        style={{ backgroundColor: "var(--bg-tertiary)", borderColor: "var(--border-default)", color: "var(--text-muted)" }}
      >
        <p className="font-medium text-[var(--text-secondary)]">Usage in Prompts</p>
        <p>
          Reference variables with <code className="text-[var(--text-primary)] bg-[var(--bg-card)] px-1 rounded">{"{{env.VARIABLE_NAME}}"}</code> in LLM prompts.
          Switch profiles for different environments.
        </p>
      </div>
    </div>
  );
}
