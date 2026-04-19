"use client";

/**
 * Inline badge showing token usage and estimated cost for an LLM step.
 * Used in RunTimeline step details.
 */

interface TokenInfo {
  input?: number | null;
  output?: number | null;
  total?: number | null;
}

interface TokenCostBadgeProps {
  tokens?: TokenInfo | null;
  modelName?: string | null;
}

// Same pricing table as backend — kept in sync for client-side display
const MODEL_PRICING: Record<string, [number, number]> = {
  "gpt-4o": [2.5, 10],
  "gpt-4o-mini": [0.15, 0.6],
  "gpt-4-turbo": [10, 30],
  "gpt-3.5-turbo": [0.5, 1.5],
  "gemini-2.5-flash": [0.15, 0.6],
  "gemini-2.5-pro": [1.25, 10],
  "gemini-2.0-flash": [0.1, 0.4],
  "gemini-1.5-pro": [1.25, 5],
  "gemini-1.5-flash": [0.075, 0.3],
  "claude-sonnet-4-20250514": [3, 15],
  "claude-3.5-sonnet": [3, 15],
  "claude-3-haiku": [0.25, 1.25],
};

function estimateCost(model: string | null | undefined, tokensIn: number, tokensOut: number): number {
  if (!model) return 0;
  let pricing = MODEL_PRICING[model];
  if (!pricing) {
    for (const [prefix, p] of Object.entries(MODEL_PRICING)) {
      if (model.startsWith(prefix)) { pricing = p; break; }
    }
  }
  if (!pricing) return 0;
  return (tokensIn / 1e6) * pricing[0] + (tokensOut / 1e6) * pricing[1];
}

function formatCost(usd: number): string {
  if (usd === 0) return "";
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  return `$${usd.toFixed(4)}`;
}

export default function TokenCostBadge({ tokens, modelName }: TokenCostBadgeProps) {
  if (!tokens || !tokens.total) return null;

  const tIn = tokens.input || 0;
  const tOut = tokens.output || 0;
  const total = tokens.total;
  const cost = estimateCost(modelName, tIn, tOut);

  return (
    <span
      className="inline-flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded-full"
      style={{
        backgroundColor: "rgba(6, 182, 212, 0.1)",
        color: "rgba(6, 182, 212, 0.8)",
        border: "1px solid rgba(6, 182, 212, 0.2)",
      }}
      title={`Input: ${tIn.toLocaleString()} | Output: ${tOut.toLocaleString()} | Total: ${total.toLocaleString()}${cost ? ` | ~${formatCost(cost)}` : ""}`}
    >
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
      </svg>
      {total.toLocaleString()} tok
      {cost > 0 && <span style={{ color: "rgba(6, 182, 212, 0.6)" }}>~{formatCost(cost)}</span>}
    </span>
  );
}
