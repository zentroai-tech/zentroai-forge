"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { cn } from "@/lib/utils";
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS, type NodeType } from "@/types/ir";
import { Tooltip } from "@/components/ui";

interface CustomNodeData {
  label: string;
  type: NodeType;
  selected?: boolean;
  onDelete?: (nodeId: string) => void;
  status?: string;
  agentColor?: string;
}

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

function CustomNode({ id, data, selected }: NodeProps<CustomNodeData>) {
  const accentColor = NODE_TYPE_COLORS[data.type] || "#64748b";

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.onDelete) data.onDelete(id);
  };

  return (
    <div
      className={cn(
        "relative group min-w-[240px] max-w-[268px] rounded-[16px] transition-all duration-150 border overflow-visible",
        selected && "ring-1"
      )}
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: selected ? `${accentColor}88` : "var(--border-default)",
        boxShadow: selected
          ? `0 0 0 1px ${accentColor}44, 0 8px 20px rgba(0, 0, 0, 0.45)`
          : "0 8px 20px rgba(0, 0, 0, 0.38)",
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3.5 !h-3.5 !-top-2 !rounded-full"
        style={{
          backgroundColor: accentColor,
          border: "1.5px solid var(--border-hover)",
          boxShadow: "0 0 0 2px rgba(13, 13, 13, 0.92)",
        }}
      />

      <Tooltip content="Delete node" side="top">
        <button
          onClick={handleDelete}
          className={cn(
            "absolute -top-2 -right-2 w-4.5 h-4.5 rounded-full z-20",
            "flex items-center justify-center",
            "bg-red-700/70 text-white",
            "opacity-0 group-hover:opacity-100 transition-opacity",
            "hover:bg-red-600/90",
            selected && "opacity-70 hover:opacity-100"
          )}
        >
          <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </Tooltip>

      {/* ── Header ── */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-[var(--border-default)]">
        <div className="flex items-center gap-2.5">
          {/* Icon container with accent tint — [&>svg] overrides the w-4 h-4 from NODE_ICONS to w-5 h-5 */}
          <span
            className="inline-flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0 [&>svg]:w-5 [&>svg]:h-5"
            style={{
              backgroundColor: `${accentColor}18`,
              color: accentColor,
            }}
          >
            {NODE_ICONS[data.type]}
          </span>
          <span className="text-[13px] font-semibold text-[var(--text-primary)] tracking-tight">
            {NODE_TYPE_LABELS[data.type]}
          </span>
        </div>
        <span className="inline-flex items-center justify-center w-4 h-4 text-[var(--text-muted)]">
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M8 5.5v13l10-6.5-10-6.5z" />
          </svg>
        </span>
      </div>

      {/* ── Body ── */}
      <div className="px-3 py-3 space-y-2">
        <div>
          <div className="text-[11px] font-medium text-[var(--text-muted)] mb-1.5">Node Name</div>
          <div className="h-9 rounded-[10px] flex items-center px-3 bg-[var(--bg-primary)]">
            <span className="text-[14px] font-semibold text-[var(--text-primary)] truncate">{data.label}</span>
          </div>
        </div>

        {data.status && (
          <div>
            <div className="text-[11px] font-medium text-[var(--text-muted)] mb-1.5">Status</div>
            <div className="h-9 rounded-[10px] border border-[var(--border-default)] flex items-center px-3 text-[13px] text-[var(--text-secondary)] bg-[var(--bg-tertiary)]">
              {data.status}
            </div>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-3.5 !h-3.5 !-bottom-2 !rounded-full"
        style={{
          backgroundColor: accentColor,
          border: "1.5px solid var(--border-hover)",
          boxShadow: "0 0 0 2px rgba(13, 13, 13, 0.92)",
        }}
      />
    </div>
  );
}

export default memo(CustomNode);
