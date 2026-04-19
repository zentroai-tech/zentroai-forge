"use client";

import type { RetrievedDoc } from "@/types/ir";

interface RetrievedDocsTableProps {
  docs: RetrievedDoc[];
}

export default function RetrievedDocsTable({ docs }: RetrievedDocsTableProps) {
  if (!docs || docs.length === 0) {
    return (
      <div className="text-xs text-[var(--text-muted)] italic">
        No documents retrieved
      </div>
    );
  }

  return (
    <div className="rounded-lg overflow-hidden border border-[var(--border-default)]">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-[var(--bg-tertiary)]">
            <th className="text-left px-3 py-2 text-[var(--text-muted)] font-medium">Score</th>
            <th className="text-left px-3 py-2 text-[var(--text-muted)] font-medium">Source</th>
            <th className="text-left px-3 py-2 text-[var(--text-muted)] font-medium">Snippet</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((doc, index) => (
            <tr
              key={doc.doc_id || index}
              className="border-t border-[var(--border-default)] hover:bg-[var(--bg-tertiary)]/50"
            >
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <div
                    className="w-12 h-1.5 rounded-full overflow-hidden bg-[var(--bg-primary)]"
                  >
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.min(doc.score * 100, 100)}%`,
                        backgroundColor: doc.score >= 0.7 ? "#4ade80" : doc.score >= 0.5 ? "#facc15" : "#f87171",
                      }}
                    />
                  </div>
                  <span
                    className="font-mono"
                    style={{
                      color: doc.score >= 0.7 ? "#4ade80" : doc.score >= 0.5 ? "#facc15" : "#f87171",
                    }}
                  >
                    {doc.score.toFixed(3)}
                  </span>
                </div>
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <svg className="w-3 h-3 text-blue-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span className="text-[var(--text-secondary)] truncate max-w-[150px]" title={doc.source}>
                    {doc.source}
                  </span>
                </div>
              </td>
              <td className="px-3 py-2">
                <p className="text-[var(--text-secondary)] line-clamp-2" title={doc.snippet}>
                  {doc.snippet}
                </p>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
