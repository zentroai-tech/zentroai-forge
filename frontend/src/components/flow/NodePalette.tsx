"use client";

import { DragEvent, useState, useMemo } from "react";
import { NODE_TYPE_LABELS, NODE_TYPE_COLORS, type NodeType } from "@/types/ir";

// ── Section definitions ──────────────────────────────────
interface Section {
  id: string;
  label: string;
  types: NodeType[];
}

const SECTIONS: Section[] = [
  {
    id: "io",
    label: "Input & Output",
    types: ["Output"],
  },
  {
    id: "models",
    label: "Models & Agents",
    types: ["LLM", "Router"],
  },
  {
    id: "orchestration",
    label: "Orchestration",
    types: ["Parallel", "Join"],
  },
  {
    id: "data",
    label: "Data & Memory",
    types: ["Retriever", "Memory"],
  },
  {
    id: "tools",
    label: "Tools & Actions",
    types: ["Tool"],
  },
  {
    id: "reliability",
    label: "Reliability",
    types: ["Error"],
  },
];

const NODE_DESCRIPTIONS: Record<NodeType, string> = {
  LLM: "Language model",
  Tool: "External tool / function",
  Router: "Conditional routing",
  Retriever: "Vector store query",
  Memory: "Conversation context",
  Output: "Final response",
  Error: "Handle runtime failures",
  Parallel: "Fan-out execution branches",
  Join: "Merge branch outputs",
};

// ── Icons (16x16 inline) ─────────────────────────────────
const NODE_ICONS: Record<NodeType, React.ReactNode> = {
  LLM: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 8V4H8" />
      <rect x="4" y="8" width="16" height="12" rx="2" />
      <path d="M2 14h2" />
      <path d="M20 14h2" />
      <path d="M9 13v2" />
      <path d="M15 13v2" />
    </svg>
  ),
  Tool: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.1-3.1a5.5 5.5 0 0 1-6.6 6.6L7 21a2 2 0 0 1-2.8-2.8l7.2-7.2a5.5 5.5 0 0 1 6.6-6.6z" />
    </svg>
  ),
  Router: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="19" r="3" />
      <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
      <circle cx="18" cy="5" r="3" />
    </svg>
  ),
  Retriever: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  ),
  Memory: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="7" ry="3" />
      <path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5" />
      <path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
    </svg>
  ),
  Output: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H7l-4 4z" />
      <path d="M11 7a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v9l-3-3h-5a2 2 0 0 1-2-2z" />
    </svg>
  ),
  Error: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z" />
      <path d="M9 9l6 6M15 9l-6 6" />
    </svg>
  ),
  Parallel: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 3h5v5" />
      <path d="M8 3H3v5" />
      <path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3" />
      <path d="m15 9 6-6" />
    </svg>
  ),
  Join: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="18" cy="18" r="3" />
      <circle cx="6" cy="6" r="3" />
      <path d="M6 21V9a9 9 0 0 0 9 9" />
    </svg>
  ),
};

interface NodePaletteProps {
  disabled?: boolean;
  hidden?: boolean;
}

type SystemConfigAction = "policies" | "retry_fallback" | "schemas";

const SYSTEM_CONFIG_ITEMS: Array<{
  id: SystemConfigAction;
  label: string;
  description: string;
  color: string;
  icon: React.ReactNode;
}> = [
  {
    id: "policies",
    label: "Policy Guard",
    description: "Allow/Deny, redaction, sanitization",
    color: "#64748B",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
  {
    id: "retry_fallback",
    label: "Retry/Fallback",
    description: "Attempts, backoff, fallback chains",
    color: "#8FA0B5",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12a9 9 0 0 1-15.5 6.3" />
        <path d="M3 12A9 9 0 0 1 18.5 5.7" />
        <path d="M3 17v-4h4" />
        <path d="M21 7v4h-4" />
      </svg>
    ),
  },
  {
    id: "schemas",
    label: "Schema Validate",
    description: "Input/output contracts for handoffs",
    color: "#7D92AA",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16v16H4z" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </svg>
    ),
  },
];

export default function NodePalette({ disabled, hidden }: NodePaletteProps) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggle = (sectionId: string) => {
    setCollapsed((prev) => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };

  const onDragStart = (event: DragEvent<HTMLDivElement>, nodeType: NodeType) => {
    event.dataTransfer.setData("application/reactflow", nodeType);
    event.dataTransfer.effectAllowed = "move";
  };

  const openSystemConfig = (target: SystemConfigAction) => {
    window.dispatchEvent(new CustomEvent("open-system-config", { detail: target }));
  };

  // Filter sections by search
  const filteredSections = useMemo(() => {
    if (!search.trim()) return SECTIONS;
    const q = search.toLowerCase();
    return SECTIONS.map((section) => ({
      ...section,
      types: section.types.filter(
        (t) =>
          NODE_TYPE_LABELS[t].toLowerCase().includes(q) ||
          NODE_DESCRIPTIONS[t].toLowerCase().includes(q)
      ),
    })).filter((s) => s.types.length > 0);
  }, [search]);

  if (hidden) return null;

  return (
    <div className="w-56 panel flex flex-col h-full overflow-hidden">
      {/* Search */}
      <div className="p-2.5">
        <div className="relative">
          <svg
            className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-muted)]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search"
            className="input-field pl-7 !py-1.5 !text-[11px]"
          />
        </div>
      </div>

      {/* Sections */}
      <div className="flex-1 overflow-y-auto px-1.5 pb-2">
        {filteredSections.map((section) => {
          const isCollapsed = collapsed[section.id];
          return (
            <div key={section.id} className="mb-1">
              {/* Section header - clickable */}
              <button
                onClick={() => toggle(section.id)}
                className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              >
                <svg
                  className={`w-3 h-3 section-chevron ${isCollapsed ? "" : "open"}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                >
                  <path d="M9 5l7 7-7 7" />
                </svg>
                {section.label}
              </button>

              {/* Items */}
              {!isCollapsed && (
                <div className="space-y-0.5">
                  {section.types.map((type) => (
                    <div
                      key={type}
                      draggable={!disabled}
                      onDragStart={(e) => onDragStart(e, type)}
                      className={`sidebar-item ${disabled ? "opacity-40 !cursor-not-allowed" : ""}`}
                    >
                      {/* Color dot */}
                      <div
                        className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0"
                        style={{
                          backgroundColor: `${NODE_TYPE_COLORS[type]}18`,
                          color: NODE_TYPE_COLORS[type],
                        }}
                      >
                        {NODE_ICONS[type]}
                      </div>
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-medium text-[var(--text-primary)] block leading-tight">
                          {NODE_TYPE_LABELS[type]}
                        </span>
                        <span className="text-[10px] text-[var(--text-muted)] block leading-tight truncate">
                          {NODE_DESCRIPTIONS[type]}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Integrations - compact */}
        <div className="mb-1">
          <button
            onClick={() => toggle("system-config")}
            className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
          >
            <svg
              className={`w-3 h-3 section-chevron ${collapsed["system-config"] ? "" : "open"}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path d="M9 5l7 7-7 7" />
            </svg>
            System Config
          </button>
          {!collapsed["system-config"] && (
            <div className="space-y-0.5">
              {SYSTEM_CONFIG_ITEMS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => openSystemConfig(item.id)}
                  className="sidebar-item w-full text-left"
                  disabled={disabled}
                >
                  <div
                    className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0"
                    style={{
                      backgroundColor: `${item.color}18`,
                      color: item.color,
                    }}
                  >
                    {item.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-medium text-[var(--text-primary)] block leading-tight">
                      {item.label}
                    </span>
                    <span className="text-[10px] text-[var(--text-muted)] block leading-tight truncate">
                      {item.description}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Integrations - compact */}
        <div className="mb-1">
          <button
            onClick={() => toggle("integrations")}
            className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
          >
            <svg
              className={`w-3 h-3 section-chevron ${collapsed["integrations"] ? "" : "open"}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path d="M9 5l7 7-7 7" />
            </svg>
            Integrations
          </button>
          {!collapsed["integrations"] && (
            <div className="px-2 pb-1">
              <div className="flex gap-1.5">
                <button
                  disabled
                  className="flex-1 px-2 py-1 text-[10px] rounded-md border border-[var(--border-default)] text-[var(--text-muted)] opacity-40"
                >
                  Telegram
                </button>
                <button
                  disabled
                  className="flex-1 px-2 py-1 text-[10px] rounded-md border border-[var(--border-default)] text-[var(--text-muted)] opacity-40"
                >
                  WhatsApp
                </button>
              </div>
              <p className="text-[9px] text-[var(--text-muted)] mt-1 text-center">Coming soon</p>
            </div>
          )}
        </div>
      </div>

      {/* Bottom */}
      <div className="p-2.5 border-t border-[var(--border-default)]">
        <button
          disabled={disabled}
          className="w-full btn-pill py-2 text-xs font-medium disabled:opacity-40 flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          Publish Agent
        </button>
      </div>
    </div>
  );
}
