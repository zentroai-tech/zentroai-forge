"use client";

import type { GuardDecision } from "@/types/ir";

interface GuardDecisionBadgeProps {
  decision: GuardDecision;
}

export default function GuardDecisionBadge({ decision }: GuardDecisionBadgeProps) {
  const isGrounded = decision.decision === "grounded";

  return (
    <div
      className={`rounded-lg p-3 border ${
        isGrounded
          ? "bg-green-500/10 border-green-500/30"
          : "bg-amber-500/10 border-amber-500/30"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isGrounded ? (
            <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          ) : (
            <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          )}
          <span
            className={`text-sm font-semibold uppercase tracking-wider ${
              isGrounded ? "text-green-400" : "text-amber-400"
            }`}
          >
            {decision.decision}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <span className="text-[var(--text-muted)]">Threshold:</span>
          <span className="ml-2 font-mono text-[var(--text-secondary)]">
            {decision.threshold.toFixed(2)}
          </span>
        </div>
        <div>
          <span className="text-[var(--text-muted)]">Top Score:</span>
          <span
            className={`ml-2 font-mono ${
              decision.top_score >= decision.threshold ? "text-green-400" : "text-amber-400"
            }`}
          >
            {decision.top_score.toFixed(3)}
          </span>
        </div>
      </div>

      {decision.reason && (
        <div className="mt-2 text-xs text-[var(--text-muted)]">
          {decision.reason}
        </div>
      )}

      {/* Score bar visualization */}
      <div className="mt-3">
        <div className="relative h-2 bg-[var(--bg-primary)] rounded-full overflow-hidden">
          {/* Threshold marker */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-white/50 z-10"
            style={{ left: `${decision.threshold * 100}%` }}
          />
          {/* Score bar */}
          <div
            className={`absolute left-0 top-0 bottom-0 rounded-full ${
              isGrounded ? "bg-green-500" : "bg-amber-500"
            }`}
            style={{ width: `${Math.min(decision.top_score * 100, 100)}%` }}
          />
        </div>
        <div className="flex justify-between mt-1 text-[10px] text-[var(--text-muted)]">
          <span>0</span>
          <span>Threshold: {decision.threshold}</span>
          <span>1</span>
        </div>
      </div>
    </div>
  );
}
