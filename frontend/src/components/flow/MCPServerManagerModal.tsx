"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { useFlowStore, type MCPServerConfig } from "@/lib/store";

interface MCPServerManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const EMPTY_FORM: MCPServerConfig = {
  id: "",
  name: "",
  command: "",
  args: [],
  cwd: "",
  env: {},
  timeout_seconds: 20,
};

export default function MCPServerManagerModal({ isOpen, onClose }: MCPServerManagerModalProps) {
  const { mcpServers, addMcpServer, updateMcpServer, removeMcpServer } = useFlowStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<MCPServerConfig>(EMPTY_FORM);
  const [argsText, setArgsText] = useState("");
  const [envJson, setEnvJson] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setEditingId(null);
    setForm(EMPTY_FORM);
    setArgsText("");
    setEnvJson("{}");
    setError(null);
  }, [isOpen]);

  if (!isOpen) return null;

  const startEdit = (server: MCPServerConfig) => {
    setEditingId(server.id);
    setForm(server);
    setArgsText(server.args.join(" "));
    setEnvJson(JSON.stringify(server.env || {}, null, 2));
    setError(null);
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setArgsText("");
    setEnvJson("{}");
    setError(null);
  };

  const handleSave = () => {
    const normalizedId = form.id.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "_");
    if (!normalizedId) {
      setError("Server ID is required.");
      return;
    }
    if (!form.name.trim()) {
      setError("Server name is required.");
      return;
    }
    if (!form.command.trim()) {
      setError("Command is required.");
      return;
    }

    let env: Record<string, string> = {};
    try {
      const parsed = JSON.parse(envJson || "{}") as Record<string, unknown>;
      env = Object.fromEntries(Object.entries(parsed).map(([k, v]) => [k, String(v)]));
    } catch {
      setError("Environment JSON is invalid.");
      return;
    }

    const payload: MCPServerConfig = {
      ...form,
      id: editingId ? editingId : normalizedId,
      args: argsText.trim() ? argsText.trim().split(/\s+/) : [],
      env,
      timeout_seconds: form.timeout_seconds || 20,
    };

    if (editingId) {
      const ok = updateMcpServer(editingId, payload);
      if (!ok) {
        setError("Failed to update server.");
        return;
      }
      toast.success("MCP server updated");
    } else {
      const ok = addMcpServer(payload);
      if (!ok) {
        setError("Server ID already exists.");
        return;
      }
      toast.success("MCP server added");
    }
    resetForm();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className="w-full max-w-5xl rounded-xl border overflow-hidden"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="h-12 px-4 flex items-center justify-between border-b" style={{ borderColor: "var(--border-default)" }}>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">MCP Servers</h2>
          <button onClick={onClose} className="btn-secondary px-2.5 py-1 text-xs">
            Close
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4">
          <div className="rounded-lg border flex flex-col min-h-[520px]" style={{ borderColor: "var(--border-default)" }}>
            <div className="section-header border-b" style={{ borderColor: "var(--border-default)" }}>Configured Servers</div>
            <div className="flex-1 overflow-auto p-2">
              {mcpServers.length === 0 && (
                <p className="px-2 py-3 text-sm text-[var(--text-muted)]">No MCP servers configured.</p>
              )}
              {mcpServers.map((server) => (
                <div
                  key={server.id}
                  className="mb-2 rounded-lg border p-3"
                  style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">{server.name}</p>
                      <p className="text-xs text-[var(--text-muted)]">{server.id}</p>
                      <p className="mt-1 text-xs text-[var(--text-secondary)]">
                        <code>{server.command} {server.args.join(" ")}</code>
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => startEdit(server)}
                        className="chip-option px-2 py-1 text-xs"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => {
                          removeMcpServer(server.id);
                          toast.success("MCP server removed");
                          if (editingId === server.id) resetForm();
                        }}
                        className="btn-secondary px-2 py-1 text-xs"
                        style={{ color: "#fda4af" }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)" }}>
            <div className="section-header px-0 pt-0 pb-2 border-b" style={{ borderColor: "var(--border-default)" }}>
              {editingId ? "Edit Server" : "New Server"}
            </div>
            <div className="space-y-2 pt-3">
              <input
                value={form.id}
                disabled={Boolean(editingId)}
                onChange={(e) => setForm((prev) => ({ ...prev, id: e.target.value }))}
                placeholder="server id (e.g. pubmed)"
                className="input-field disabled:opacity-60"
              />
              <input
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="display name"
                className="input-field"
              />
              <input
                value={form.command}
                onChange={(e) => setForm((prev) => ({ ...prev, command: e.target.value }))}
                placeholder="command (e.g. npx)"
                className="input-field"
              />
              <input
                value={argsText}
                onChange={(e) => setArgsText(e.target.value)}
                placeholder="args (space-separated)"
                className="input-field"
              />
              <input
                value={form.cwd || ""}
                onChange={(e) => setForm((prev) => ({ ...prev, cwd: e.target.value }))}
                placeholder="cwd (optional)"
                className="input-field"
              />
              <input
                type="number"
                value={form.timeout_seconds || 20}
                min={1}
                onChange={(e) => setForm((prev) => ({ ...prev, timeout_seconds: parseFloat(e.target.value) || 20 }))}
                placeholder="timeout seconds"
                className="input-field"
              />
              <textarea
                value={envJson}
                onChange={(e) => setEnvJson(e.target.value)}
                placeholder='env JSON, e.g. {"NODE_ENV":"production"}'
                className="input-field min-h-[140px] resize-y font-mono text-xs"
              />
              {error && <p className="msg-error-soft text-xs">{error}</p>}
              <div className="flex justify-end gap-2 pt-1">
                <button onClick={resetForm} className="btn-secondary px-3 py-1.5 text-xs">
                  Reset
                </button>
                <button onClick={handleSave} className="btn-primary px-3 py-1.5 text-xs">
                  {editingId ? "Update" : "Add"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
