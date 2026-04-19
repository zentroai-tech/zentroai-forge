"use client";

import type { Citation } from "@/types/ir";

interface CitationsListProps {
  citations: Citation[];
  isGrounded?: boolean;
}

export default function CitationsList({ citations, isGrounded = true }: CitationsListProps) {
  // Show warning if grounded but no citations
  if (isGrounded && (!citations || citations.length === 0)) {
    return (
      <div className="rounded-lg p-3 bg-red-500/10 border border-red-500/30">
        <div className="flex items-center gap-2 text-red-400">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium">Grounded response without citations</span>
        </div>
        <p className="text-xs text-red-400/80 mt-1">
          The response was marked as grounded but no citations were provided.
        </p>
      </div>
    );
  }

  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
        <span>{citations.length} citation{citations.length !== 1 ? "s" : ""}</span>
      </div>

      <div className="space-y-2">
        {citations.map((citation, index) => (
          <div
            key={citation.doc_id || index}
            className="rounded-lg p-3 bg-[var(--bg-tertiary)] border border-[var(--border-default)]"
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-mono text-[var(--text-primary)] bg-[var(--bg-card)] px-1.5 py-0.5 rounded">
                [{index + 1}]
              </span>
              <span className="text-xs text-[var(--text-secondary)] truncate flex-1" title={citation.source}>
                {citation.source}
              </span>
            </div>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
              &ldquo;{citation.text}&rdquo;
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
