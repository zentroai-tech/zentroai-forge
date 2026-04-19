"use client";

import { useMemo, useRef, useState } from "react";
import type { FlowIRv2 } from "@/types/agents";
import ToolsPanel from "@/components/flow/ToolsPanel";

interface IRJsonModalProps {
  isOpen: boolean;
  onClose: () => void;
  ir: FlowIRv2 | null;
}

type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];
type JsonObject = { [key: string]: JsonValue };

function formatTypeLabel(value: JsonValue): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return `array(${value.length})`;
  if (typeof value === "object") return "object";
  return typeof value;
}

function JsonNode({ label, value, depth = 0 }: { label: string; value: JsonValue; depth?: number }) {
  const isContainer = value !== null && typeof value === "object";
  const indent = `${depth * 12}px`;

  if (!isContainer) {
    return (
      <div className="py-1 text-xs" style={{ paddingLeft: indent }}>
        <span style={{ color: "var(--text-muted)" }}>{label}: </span>
        <span style={{ color: "var(--text-primary)" }}>{String(value)}</span>
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <details open={depth < 2} className="py-0.5">
        <summary className="cursor-pointer text-xs" style={{ paddingLeft: indent, color: "var(--text-secondary)" }}>
          {label} <span style={{ color: "var(--text-muted)" }}>({formatTypeLabel(value)})</span>
        </summary>
        <div className="mt-1">
          {value.map((item, idx) => (
            <JsonNode key={`${label}-${idx}`} label={`[${idx}]`} value={item} depth={depth + 1} />
          ))}
        </div>
      </details>
    );
  }

  return (
    <details open={depth < 2} className="py-0.5">
      <summary className="cursor-pointer text-xs" style={{ paddingLeft: indent, color: "var(--text-secondary)" }}>
        {label} <span style={{ color: "var(--text-muted)" }}>({formatTypeLabel(value)})</span>
      </summary>
      <div className="mt-1">
        {Object.entries(value).map(([k, v]) => (
          <JsonNode key={`${label}-${k}`} label={k} value={v} depth={depth + 1} />
        ))}
      </div>
    </details>
  );
}

export default function IRJsonModal({ isOpen, onClose, ir }: IRJsonModalProps) {
  const [tab, setTab] = useState<"ir" | "tools">("ir");
  const [view, setView] = useState<"tree" | "raw">("tree");
  const [searchText, setSearchText] = useState("");
  const [searchStatus, setSearchStatus] = useState<string | null>(null);
  const [currentMatchPointer, setCurrentMatchPointer] = useState<number>(-1);
  const rawTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const rawJson = useMemo(() => JSON.stringify(ir || {}, null, 2), [ir]);
  const rootValue = useMemo(() => (ir || {}) as JsonObject, [ir]);
  const normalizedQuery = useMemo(() => searchText.trim().toLowerCase(), [searchText]);
  const matchIndexes = useMemo(() => {
    if (!normalizedQuery) return [] as number[];
    const haystack = rawJson.toLowerCase();
    const hits: number[] = [];
    let from = 0;
    while (from < haystack.length) {
      const idx = haystack.indexOf(normalizedQuery, from);
      if (idx < 0) break;
      hits.push(idx);
      from = idx + Math.max(1, normalizedQuery.length);
    }
    return hits;
  }, [rawJson, normalizedQuery]);

  const focusMatch = (pointer: number) => {
    if (!normalizedQuery) {
      setSearchStatus("Enter text to search.");
      return;
    }
    if (matchIndexes.length === 0) {
      setSearchStatus("No matches.");
      setCurrentMatchPointer(-1);
      return;
    }
    const nextPointer = ((pointer % matchIndexes.length) + matchIndexes.length) % matchIndexes.length;
    const index = matchIndexes[nextPointer];
    if (view !== "raw") {
      setView("raw");
    }
    setCurrentMatchPointer(nextPointer);
    setSearchStatus(`Match ${nextPointer + 1}/${matchIndexes.length} at position ${index + 1}.`);

    requestAnimationFrame(() => {
      const el = rawTextareaRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(index, index + normalizedQuery.length);
      const lineHeight = 18;
      const linesBefore = rawJson.slice(0, index).split("\n").length - 1;
      el.scrollTop = Math.max(0, linesBefore * lineHeight - 80);
    });
  };

  const handleNext = () => {
    if (currentMatchPointer < 0) {
      focusMatch(0);
      return;
    }
    focusMatch(currentMatchPointer + 1);
  };

  const handlePrev = () => {
    if (currentMatchPointer < 0) {
      focusMatch(matchIndexes.length - 1);
      return;
    }
    focusMatch(currentMatchPointer - 1);
  };

  const handleExportJson = () => {
    const blob = new Blob([rawJson], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ir.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div
        className="w-full max-w-5xl overflow-hidden rounded-xl border shadow-2xl"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border-default)" }}>
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
              IR JSON Explorer
            </h2>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              Browse the exact IR payload that Forge saves/exports
            </p>
          </div>
          <div className="flex items-center gap-2">
            {tab === "ir" && (
              <>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(rawJson);
                    } catch {
                      // noop
                    }
                  }}
                  className="btn-secondary text-xs"
                >
                  Copy JSON
                </button>
                <button type="button" onClick={handleExportJson} className="btn-secondary text-xs">
                  Export ir.json
                </button>
              </>
            )}
            <button onClick={onClose} className="btn-secondary text-xs">Close</button>
          </div>
        </div>

        {/* Top-level tab bar: IR / Tools */}
        <div className="flex items-center gap-1 border-b px-4 py-2" style={{ borderColor: "var(--border-default)" }}>
          <button
            type="button"
            onClick={() => setTab("ir")}
            className={`btn-secondary text-xs ${tab === "ir" ? "active" : ""}`}
          >
            IR JSON
          </button>
          <button
            type="button"
            onClick={() => setTab("tools")}
            className={`btn-secondary text-xs ${tab === "tools" ? "active" : ""}`}
          >
            Tools
          </button>
        </div>

        {tab === "tools" ? (
          <div className="h-[66vh] overflow-auto">
            <ToolsPanel ir={ir} />
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2 border-b px-4 py-2" style={{ borderColor: "var(--border-default)" }}>
              <button
                type="button"
                onClick={() => setView("tree")}
                className={`btn-secondary text-xs ${view === "tree" ? "active" : ""}`}
              >
                Tree
              </button>
              <button
                type="button"
                onClick={() => setView("raw")}
                className={`btn-secondary text-xs ${view === "raw" ? "active" : ""}`}
              >
                Raw
              </button>
              <div className="ml-auto flex items-center gap-2">
                <input
                  value={searchText}
                  onChange={(e) => {
                    setSearchText(e.target.value);
                    setSearchStatus(null);
                    setCurrentMatchPointer(-1);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleNext();
                  }}
                  placeholder="Search in IR JSON..."
                  className="input-field h-8 w-52 text-xs"
                />
                <button type="button" onClick={handlePrev} className="btn-secondary text-xs">
                  Prev
                </button>
                <button type="button" onClick={handleNext} className="btn-secondary text-xs">
                  Next
                </button>
              </div>
            </div>

            <div className="p-4">
              {view === "tree" ? (
                <div
                  className="h-[62vh] overflow-auto rounded-lg border p-3"
                  style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}
                >
                  <JsonNode label="ir.json" value={rootValue} />
                </div>
              ) : (
                <textarea
                  ref={rawTextareaRef}
                  value={rawJson}
                  readOnly
                  className="input-field h-[62vh] w-full font-mono text-xs"
                  spellCheck={false}
                />
              )}
              {searchStatus && (
                <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                  {searchStatus}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
