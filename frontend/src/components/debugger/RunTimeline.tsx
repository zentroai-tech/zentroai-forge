"use client";

import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { getRun, deleteRun } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/utils";
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from "@/types/ir";
import type { Run, TimelineStep, NodeType } from "@/types/ir";
import RetrievedDocsTable from "./RetrievedDocsTable";
import GuardDecisionBadge from "./GuardDecisionBadge";
import CitationsList from "./CitationsList";
import RunReplayButton from "./RunReplayButton";
import RunComparison from "./RunComparison";
import TokenCostBadge from "./TokenCostBadge";
import { CredentialErrorBanner } from "@/components/credentials";
import type { CredentialError, CredentialProvider } from "@/types/credentials";

interface RunTimelineProps {
  runId: string;
  onNavigateToRun?: (runId: string) => void;
  onOpenSettings?: (scope: "workspace" | "project") => void;
  onRunDeleted?: (runId: string) => void;
}

// Parse error message to detect credential errors
function parseCredentialError(errorMessage: string): CredentialError | null {
  // Check for common credential error patterns
  const patterns = [
    { regex: /OPENAI_API_KEY/i, provider: "openai" as CredentialProvider },
    { regex: /openai.*api[_\s]?key/i, provider: "openai" as CredentialProvider },
    { regex: /ANTHROPIC_API_KEY/i, provider: "anthropic" as CredentialProvider },
    { regex: /anthropic.*api[_\s]?key/i, provider: "anthropic" as CredentialProvider },
    { regex: /GOOGLE_API_KEY/i, provider: "gemini" as CredentialProvider },
    { regex: /google.*api[_\s]?key/i, provider: "gemini" as CredentialProvider },
    { regex: /gemini.*api[_\s]?key/i, provider: "gemini" as CredentialProvider },
  ];

  for (const { regex, provider } of patterns) {
    if (regex.test(errorMessage)) {
      return {
        type: "missing_credential",
        provider,
        scope: "workspace",
        message: errorMessage,
      };
    }
  }

  return null;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") {
    return (
      <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="7" fill="#10B981" fillOpacity="0.2" stroke="#10B981" strokeWidth="1.5" />
        <path d="M5 8l2.5 2.5L11 5.5" stroke="#10B981" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="7" fill="#EF4444" fillOpacity="0.2" stroke="#EF4444" strokeWidth="1.5" />
        <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="#EF4444" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (status === "running") {
    return (
      <svg className="w-3.5 h-3.5 flex-shrink-0 animate-spin" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="6" stroke="#3B82F6" strokeWidth="1.5" strokeOpacity="0.3" />
        <path d="M8 2a6 6 0 016 6" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (status === "skipped") {
    return (
      <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="7" fill="#6B7280" fillOpacity="0.15" stroke="#6B7280" strokeWidth="1.5" />
        <path d="M6 5.5l3 2.5-3 2.5" stroke="#9CA3AF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="7" fill="#6B7280" fillOpacity="0.15" stroke="#6B7280" strokeWidth="1.5" />
      <circle cx="8" cy="8" r="2" fill="#9CA3AF" />
    </svg>
  );
}

export default function RunTimeline({ runId, onNavigateToRun, onOpenSettings, onRunDeleted }: RunTimelineProps) {
  const [run, setRun] = useState<Run | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [inputExpanded, setInputExpanded] = useState(false);
  const [outputExpanded, setOutputExpanded] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("all");

  const loadRun = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getRun(runId);
      setRun(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load run");
    } finally {
      setIsLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    loadRun();
  }, [loadRun]);

  useEffect(() => {
    if (!run) return;
    const agentIds = new Set(
      [
        ...(run.timeline ?? []).map((step) => step.agent_id).filter(Boolean),
        ...(run.agent_events ?? []).map((evt) => evt.agent_id).filter(Boolean),
      ] as string[]
    );
    if (selectedAgentId !== "all" && !agentIds.has(selectedAgentId)) {
      setSelectedAgentId("all");
    }
  }, [run, selectedAgentId]);

  const toggleStep = (index: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  if (isLoading && !run) {
    return (
      <div className="flex items-center justify-center h-full">
        <p style={{ color: "var(--text-muted)" }}>Loading...</p>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center h-full">
        <p style={{ color: "var(--text-muted)" }}>Run not found</p>
      </div>
    );
  }

  const getStatusStyle = (status: string) => {
    switch (status) {
      case "completed":
        return { bg: "rgba(34, 197, 94, 0.2)", text: "#4ade80" };
      case "failed":
        return { bg: "rgba(239, 68, 68, 0.2)", text: "#f87171" };
      case "running":
        return { bg: "rgba(59, 130, 246, 0.2)", text: "#60a5fa" };
      default:
        return { bg: "rgba(234, 179, 8, 0.2)", text: "#facc15" };
    }
  };

  const statusStyle = getStatusStyle(run.status);
  const allAgentIds = Array.from(
    new Set(
      [
        ...(run.timeline ?? []).map((step) => step.agent_id).filter(Boolean),
        ...(run.agent_events ?? []).map((evt) => evt.agent_id).filter(Boolean),
      ] as string[]
    )
  );
  const filteredTimeline =
    selectedAgentId === "all"
      ? run.timeline ?? []
      : (run.timeline ?? []).filter((step) => step.agent_id === selectedAgentId);
  const filteredAgentEvents =
    selectedAgentId === "all"
      ? run.agent_events ?? []
      : (run.agent_events ?? []).filter((evt) => evt.agent_id === selectedAgentId);

  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-auto p-4">
      {/* Run header */}
      <div
        className="mb-6 p-4 rounded-xl"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-white">Run Details</h3>
          <div className="flex items-center gap-2">
            <RunReplayButton
              runId={runId}
              onReplayCreated={(newRunId) => {
                if (onNavigateToRun) {
                  onNavigateToRun(newRunId);
                }
              }}
            />
            {showDeleteConfirm ? (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-red-400 mr-1">Delete?</span>
                <button
                  onClick={async () => {
                    setIsDeleting(true);
                    try {
                      await deleteRun(runId);
                      toast.success("Run deleted");
                      onRunDeleted?.(runId);
                    } catch (error) {
                      toast.error(error instanceof Error ? error.message : "Failed to delete");
                    } finally {
                      setIsDeleting(false);
                      setShowDeleteConfirm(false);
                    }
                  }}
                  disabled={isDeleting}
                  className="text-xs px-2.5 py-1 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                >
                  {isDeleting ? "..." : "Yes"}
                </button>
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="text-xs px-2.5 py-1 rounded-lg transition-colors"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
                >
                  No
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="p-1.5 rounded-md transition-colors hover:bg-red-500/20"
                style={{ color: "var(--text-muted)" }}
                title="Delete run"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
            <button
              onClick={loadRun}
              disabled={isLoading}
              className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
              style={{ color: "var(--text-muted)" }}
              title="Refresh"
            >
              <svg className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span style={{ color: "var(--text-muted)" }}>ID:</span>{" "}
            <span className="font-mono text-xs text-white">{run.id}</span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Status:</span>{" "}
            <span
              className="px-2 py-0.5 rounded-full text-xs"
              style={{ backgroundColor: statusStyle.bg, color: statusStyle.text }}
            >
              {run.status}
            </span>
          </div>
          <div style={{ color: "var(--text-secondary)" }}>
            <span style={{ color: "var(--text-muted)" }}>Created:</span> {formatDate(run.created_at)}
          </div>
          {run.started_at && (
            <div style={{ color: "var(--text-secondary)" }}>
              <span style={{ color: "var(--text-muted)" }}>Started:</span> {formatDate(run.started_at)}
            </div>
          )}
        </div>

        <div
          className="mt-3 pt-3 border-t"
          style={{ borderColor: "var(--border-default)" }}
        >
          <button
            type="button"
            onClick={() => setInputExpanded((v) => !v)}
            className="w-full flex items-center gap-2 text-left text-xs mb-1"
            style={{ color: "var(--text-muted)" }}
          >
            <svg
              className={`w-4 h-4 transition-transform flex-shrink-0 ${inputExpanded ? "rotate-90" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span>Input</span>
          </button>
          {inputExpanded && (
            <pre
              className="text-sm p-2 rounded overflow-x-auto mt-1"
              style={{
                backgroundColor: "var(--bg-tertiary)",
                border: "1px solid var(--border-default)",
                color: "var(--text-secondary)",
              }}
            >
              {JSON.stringify(run.input, null, 2)}
            </pre>
          )}
        </div>

        {run.output && (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setOutputExpanded((v) => !v)}
              className="w-full flex items-center gap-2 text-left text-xs mb-1"
              style={{ color: "var(--text-muted)" }}
            >
              <svg
                className={`w-4 h-4 transition-transform flex-shrink-0 ${outputExpanded ? "rotate-90" : ""}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span>Output</span>
            </button>
            {outputExpanded && (
              <pre
                className="text-sm p-2 rounded overflow-x-auto mt-1"
                style={{
                  backgroundColor: "var(--bg-tertiary)",
                  border: "1px solid var(--border-default)",
                  color: "var(--text-secondary)",
                }}
              >
                {JSON.stringify(run.output, null, 2)}
              </pre>
            )}
          </div>
        )}

        {run.error_message && (() => {
          const credentialError = parseCredentialError(run.error_message);
          if (credentialError && onOpenSettings) {
            return (
              <div className="mt-3">
                <CredentialErrorBanner
                  error={credentialError}
                  onOpenSettings={onOpenSettings}
                />
              </div>
            );
          }
          return (
            <div className="mt-3">
              <p className="text-xs mb-1" style={{ color: "#f87171" }}>Error:</p>
              <p
                className="text-sm p-2 rounded"
                style={{
                  backgroundColor: "rgba(239, 68, 68, 0.1)",
                  border: "1px solid rgba(239, 68, 68, 0.2)",
                  color: "#f87171",
                }}
              >
                {run.error_message}
              </p>
            </div>
          );
        })()}

        {/* Citations */}
        {run.citations && run.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t" style={{ borderColor: "var(--border-default)" }}>
            <CitationsList citations={run.citations} isGrounded={true} />
          </div>
        )}
      </div>

      {/* Comparison with original run */}
      {run.original_run_id && (
        <div className="mb-6">
          <RunComparison runId={run.id} originalRunId={run.original_run_id} />
        </div>
      )}

      {/* Steps timeline */}
      <div className="mb-4 flex items-center justify-between gap-3">
        <h4 className="font-semibold text-white">Execution Timeline</h4>
        {allAgentIds.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>Agent</span>
            <select
              value={selectedAgentId}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              className="rounded-lg px-2.5 py-1.5 text-xs"
              style={{
                backgroundColor: "var(--bg-secondary)",
                border: "1px solid var(--border-default)",
                color: "var(--text-secondary)",
              }}
            >
              <option value="all">All</option>
              {allAgentIds.map((agentId) => (
                <option key={agentId} value={agentId}>{agentId}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!filteredTimeline || filteredTimeline.length === 0 ? (
        <p className="text-sm text-center py-4" style={{ color: "var(--text-muted)" }}>No steps recorded</p>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div
            className="absolute left-4 top-0 bottom-0 w-0.5"
            style={{ backgroundColor: "var(--border-default)" }}
          />

          {/* Agent events summary for v2 flows */}
          {filteredAgentEvents && filteredAgentEvents.length > 0 && (
            <div className="mb-4 ml-10 p-3 rounded-lg border" style={{ borderColor: "var(--border-default)", backgroundColor: "rgba(124, 58, 237, 0.05)" }}>
              <div className="text-xs font-medium text-violet-400 mb-2">Agent Timeline</div>
              <div className="flex flex-wrap gap-1">
                {filteredAgentEvents.map((evt) => {
                  const eventType = (evt.event_type || "").toLowerCase();
                  const eventData = (evt.data as Record<string, string>) || {};
                  const className =
                    eventType === "handoff"
                      ? "bg-amber-900/30 text-amber-300"
                      : eventType === "agent_start"
                      ? "bg-emerald-900/30 text-emerald-300"
                      : eventType === "budget_exceeded" || eventType === "schema_validation_error" || eventType === "guard_block"
                      ? "bg-red-900/30 text-red-300"
                      : eventType === "retry_attempt" || eventType === "fallback_used" || eventType === "budget_warning"
                      ? "bg-sky-900/30 text-sky-300"
                      : "bg-zinc-800 text-zinc-400";

                  const label =
                    eventType === "handoff"
                      ? `${eventData.from_agent ?? "?"} -> ${eventData.to_agent ?? "?"}`
                      : eventType === "retry_attempt"
                      ? `RETRY ${evt.agent_id}`
                      : eventType === "fallback_used"
                      ? `FALLBACK ${evt.agent_id}`
                      : eventType === "schema_validation_error"
                      ? `SCHEMA ${evt.agent_id}`
                      : eventType === "guard_block"
                      ? `GUARD ${evt.agent_id}`
                      : `${eventType.replace("agent_", "").toUpperCase()} ${evt.agent_id}`;

                  return (
                    <span key={evt.id} className={`text-[10px] px-2 py-0.5 rounded ${className}`} title={JSON.stringify(evt.data ?? {})}>
                      {label}
                    </span>
                  );
                })}
                
              </div>
            </div>
          )}

          <div className="space-y-4">
            {filteredTimeline.map((step, index) => (
              <StepCard
                key={step.step_id || index}
                step={step}
                index={index}
                expanded={expandedSteps.has(index)}
                onToggle={() => toggleStep(index)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Resolve tokens and model for TokenCostBadge: prefer API fields, fallback to step.output for LLM nodes
function getStepTokensAndModel(step: TimelineStep): { tokens: TimelineStep["tokens"]; modelName: string | null } {
  if (step.tokens?.total != null) {
    return { tokens: step.tokens, modelName: step.model_name ?? null };
  }
  const nodeType = (step.node_type ?? "").toString().toUpperCase();
  if (nodeType !== "LLM") {
    return { tokens: step.tokens ?? null, modelName: step.model_name ?? null };
  }
  let raw: Record<string, unknown> | null = null;
  if (step.output != null) {
    if (typeof step.output === "object" && !Array.isArray(step.output)) {
      raw = step.output as Record<string, unknown>;
    } else if (typeof step.output === "string") {
      try {
        const parsed = JSON.parse(step.output) as unknown;
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) raw = parsed as Record<string, unknown>;
      } catch {
        // ignore
      }
    }
  }
  if (!raw) return { tokens: step.tokens ?? null, modelName: step.model_name ?? null };
  const tokensUsed = raw.tokens_used;
  const modelName = (typeof raw.model === "string" ? raw.model : step.model_name) ?? null;
  if (tokensUsed == null) return { tokens: null, modelName };
  let tokens: { input?: number; output?: number; total: number } | null = null;
  const toNum = (v: unknown): number | undefined =>
    typeof v === "number" && !Number.isNaN(v) ? v : typeof v === "string" ? parseInt(v, 10) : undefined;
  if (typeof tokensUsed === "number" && !Number.isNaN(tokensUsed)) {
    tokens = { total: tokensUsed };
  } else if (typeof tokensUsed === "string") {
    const n = parseInt(tokensUsed, 10);
    if (!Number.isNaN(n)) tokens = { total: n };
  } else if (typeof tokensUsed === "object" && tokensUsed !== null && typeof (tokensUsed as Record<string, unknown>).total === "number") {
    const t = tokensUsed as Record<string, unknown>;
    tokens = {
      input: toNum(t.input ?? t.prompt_tokens),
      output: toNum(t.output ?? t.completion_tokens),
      total: (t.total as number) ?? 0,
    };
    if (!tokens.total && (tokens.input != null || tokens.output != null)) {
      tokens.total = (tokens.input ?? 0) + (tokens.output ?? 0);
    }
  } else if (typeof tokensUsed === "object" && tokensUsed !== null) {
    const t = tokensUsed as Record<string, unknown>;
    const input = toNum(t.input ?? t.prompt_tokens) ?? 0;
    const output = toNum(t.output ?? t.completion_tokens) ?? 0;
    const total = toNum(t.total) ?? input + output;
    if (total > 0) tokens = { input: input || undefined, output: output || undefined, total };
  }
  return { tokens, modelName };
}

interface StepCardProps {
  step: TimelineStep;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}

function StepCard({ step, index, expanded, onToggle }: StepCardProps) {
  const nodeType = step.node_type.toUpperCase() as NodeType;
  const nodeColor = NODE_TYPE_COLORS[nodeType] || "#64748b";
  const { tokens: stepTokens, modelName: stepModelName } = getStepTokensAndModel(step);
  const duration = step.started_at && step.finished_at
    ? formatDuration(new Date(step.started_at).getTime(), new Date(step.finished_at).getTime())
    : step.started_at ? "running..." : "pending";

  const getStepStyle = () => {
    if (step.status === "failed") {
      return { bg: "rgba(239, 68, 68, 0.1)", border: "rgba(239, 68, 68, 0.3)" };
    }
    if (step.status === "completed") {
      return { bg: "rgba(34, 197, 94, 0.1)", border: "rgba(34, 197, 94, 0.3)" };
    }
    return { bg: "var(--bg-secondary)", border: "var(--border-default)" };
  };

  const stepStyle = getStepStyle();

  return (
    <div className="relative pl-10">
      {/* Timeline dot */}
      <div
        className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2"
        style={{ backgroundColor: nodeColor, borderColor: "var(--bg-primary)" }}
      />

      <div
        className="p-3 rounded-xl border transition-colors"
        style={{ backgroundColor: stepStyle.bg, borderColor: stepStyle.border }}
      >
        <button
          onClick={onToggle}
          className="w-full text-left min-w-0"
        >
          <div className="flex items-center justify-between gap-3 min-w-0">
            <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
              <StatusIcon status={step.status} />
              <span
                className="text-xs font-medium px-2 py-0.5 rounded flex-shrink-0"
                style={{ backgroundColor: `${nodeColor}20`, color: nodeColor }}
              >
                {NODE_TYPE_LABELS[nodeType] || step.node_type}
              </span>
              <span className="text-sm font-medium text-white truncate min-w-0" title={step.node_id}>{step.node_id}</span>
              {step.agent_id && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/40 text-violet-300 flex-shrink-0">
                  {step.agent_id}{step.depth ? ` d${step.depth}` : ""}
                </span>
              )}
            </div>
            <div
              className="flex items-center gap-2 text-xs flex-shrink-0"
              style={{ color: "var(--text-muted)" }}
            >
              <TokenCostBadge tokens={stepTokens} modelName={stepModelName} />
              <span>{duration}</span>
              <svg
                className={`w-4 h-4 transition-transform ${expanded ? "rotate-180" : ""}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </button>

        {expanded && (
          <div
            className="mt-3 pt-3 border-t space-y-3"
            style={{ borderColor: "var(--border-default)" }}
          >
            <div className="grid grid-cols-2 gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
              {step.started_at && (
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Started:</span>{" "}
                  {formatDate(step.started_at)}
                </div>
              )}
              {step.finished_at && (
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Ended:</span>{" "}
                  {formatDate(step.finished_at)}
                </div>
              )}
            </div>

            {step.input && Object.keys(step.input).length > 0 && (
              <div>
                <p className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Input:</p>
                <pre
                  className="text-xs p-2 rounded overflow-x-auto"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {JSON.stringify(step.input, null, 2)}
                </pre>
              </div>
            )}

            {step.output && Object.keys(step.output).length > 0 && (
              <div>
                <p className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Output:</p>
                <pre
                  className="text-xs p-2 rounded overflow-x-auto"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {JSON.stringify(step.output, null, 2)}
                </pre>
              </div>
            )}

            {step.meta && Object.keys(step.meta).length > 0 && (
              <div>
                <p className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Metadata:</p>
                <pre
                  className="text-xs p-2 rounded overflow-x-auto"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {JSON.stringify(step.meta, null, 2)}
                </pre>
              </div>
            )}

            {/* Retrieved Documents (for Retriever steps) */}
            {step.retrieved_docs && step.retrieved_docs.length > 0 && (
              <div>
                <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
                  Retrieved Documents ({step.retrieved_docs.length})
                </p>
                <RetrievedDocsTable docs={step.retrieved_docs} />
              </div>
            )}

            {/* Guard Decision (for Router/Guard steps) */}
            {step.guard_decision && (
              <div>
                <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>Guard Decision</p>
                <GuardDecisionBadge decision={step.guard_decision} />
              </div>
            )}

            {/* Citations (for Output steps) */}
            {step.citations && (
              <div>
                <CitationsList
                  citations={step.citations}
                  isGrounded={step.guard_decision?.decision === "grounded"}
                />
              </div>
            )}

            {step.error_message && (
              <div>
                <p className="text-xs mb-1" style={{ color: "#f87171" }}>Error:</p>
                <p
                  className="text-xs p-2 rounded"
                  style={{
                    backgroundColor: "rgba(239, 68, 68, 0.1)",
                    color: "#f87171",
                  }}
                >
                  {step.error_message}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
