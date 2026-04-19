"use client";

import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  module?: string;
  run_id?: string;
  node_id?: string;
  node_type?: string;
}

interface LogViewerProps {
  onClose: () => void;
  embedded?: boolean;
}

export default function LogViewer({ onClose, embedded }: LogViewerProps) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [level, setLevel] = useState("INFO");
  const [search, setSearch] = useState("");
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const appendEntry = useCallback((entry: LogEntry) => {
    setEntries((prev) => [...prev.slice(-499), entry]);
  }, []);

  useEffect(() => {
    const url = `${API_BASE}/logs/stream?level=${encodeURIComponent(level)}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data) as LogEntry;
        appendEntry(entry);
      } catch {
        // ignore malformed
      }
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
      setConnected(false);
    };
  }, [level, appendEntry]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  const filtered = search.trim()
    ? entries.filter(
        (e) =>
          e.message.toLowerCase().includes(search.toLowerCase()) ||
          (e.run_id && e.run_id.toLowerCase().includes(search.toLowerCase())) ||
          (e.node_id && e.node_id.toLowerCase().includes(search.toLowerCase()))
      )
    : entries;

  const toolbar = (
    <div className="px-4 py-2 border-b flex items-center justify-between flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${connected ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}`}
      >
        {connected ? "Live" : "Disconnected"}
      </span>
      <div className="flex items-center gap-2">
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="rounded-lg px-2 py-1 text-xs"
          style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
        >
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter message, run_id, node_id..."
          className="rounded-lg px-3 py-1.5 text-xs w-48"
          style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
        />
        <button
          onClick={() => setEntries([])}
          className="px-2 py-1.5 rounded-lg text-xs hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-muted)" }}
        >
          Clear
        </button>
      </div>
    </div>
  );

  const logContent = (
    <div
          ref={containerRef}
          className="flex-1 overflow-y-auto p-2 font-mono text-xs"
          style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
        >
          {filtered.length === 0 && (
            <div className="flex items-center justify-center h-full text-[var(--text-muted)]">
              {entries.length === 0 ? "Waiting for logs..." : "No entries match the filter."}
            </div>
          )}
          {filtered.map((e, i) => (
            <div
              key={i}
              className="py-1 px-2 rounded border-b border-[var(--border-default)]/50 hover:bg-[var(--bg-tertiary)]/50"
            >
              <span className="text-[var(--text-muted)] mr-2">{e.timestamp?.replace("T", " ").slice(0, 19)}</span>
              <span
                className={`font-medium ${
                  e.level === "ERROR"
                    ? "text-red-400"
                    : e.level === "WARNING"
                    ? "text-amber-400"
                    : e.level === "DEBUG"
                    ? "text-[var(--text-muted)]"
                    : "text-[var(--text-secondary)]"
                }`}
              >
                [{e.level}]
              </span>
              {(e.run_id || e.node_id) && (
                <span className="ml-2 text-[var(--text-muted)]">
                  {e.run_id && `run=${e.run_id.slice(0, 12)}`}
                  {e.node_id && ` node=${e.node_id}`}
                </span>
              )}
              <span className="ml-2 break-all">{e.message}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
  );

  if (embedded) return (
    <div className="h-full flex flex-col">
      {toolbar}
      {logContent}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-4xl mx-4 h-[85vh] flex flex-col border"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="p-4 border-b flex items-center justify-between flex-shrink-0" style={{ borderColor: "var(--border-default)" }}>
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-white">Log Viewer</h2>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${connected ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}`}
            >
              {connected ? "Live" : "Disconnected"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              className="rounded-lg px-2 py-1 text-xs"
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
            >
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter message, run_id, node_id..."
              className="rounded-lg px-3 py-1.5 text-xs w-48"
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
            />
            <button
              onClick={() => setEntries([])}
              className="px-2 py-1.5 rounded-lg text-xs hover:bg-[var(--bg-tertiary)]"
              style={{ color: "var(--text-muted)" }}
            >
              Clear
            </button>
            <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--bg-tertiary)]" style={{ color: "var(--text-muted)" }}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {logContent}
      </div>
    </div>
  );
}
