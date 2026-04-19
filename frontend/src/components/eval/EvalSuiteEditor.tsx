"use client";

import React from "react";
import { useState, useCallback } from "react";
import toast from "react-hot-toast";
import type { EvalCase } from "@/types/eval";
import * as api from "@/lib/evalsApi";

/* ------------------------------------------------------------------ */
/*  Props                                                             */
/* ------------------------------------------------------------------ */

interface EvalSuiteEditorProps {
  suiteId: string;
  cases: EvalCase[];
  /** Called after a case is created so the parent can re-fetch. */
  onCasesChanged: () => void;
}

/* ------------------------------------------------------------------ */
/*  ChipsInput (reusable tags editor)                                 */
/* ------------------------------------------------------------------ */

interface ChipsInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder: string;
}

function ChipsInput({ value, onChange, placeholder }: ChipsInputProps) {
  const [inputValue, setInputValue] = useState("");

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && inputValue.trim()) {
      e.preventDefault();
      if (!value.includes(inputValue.trim())) {
        onChange([...value, inputValue.trim()]);
      }
      setInputValue("");
    } else if (e.key === "Backspace" && !inputValue && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div
      className="input-field min-h-[38px] flex flex-wrap items-center gap-1.5 p-1.5 cursor-text"
      onClick={(e) => (e.currentTarget.querySelector("input") as HTMLInputElement)?.focus()}
    >
      {value.map((chip, index) => (
        <span
          key={index}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
        >
          {chip}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onChange(value.filter((_, i) => i !== index));
            }}
            className="hover:text-white"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </span>
      ))}
      <input
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={value.length === 0 ? placeholder : ""}
        className="flex-1 min-w-[100px] bg-transparent border-none outline-none text-sm text-white placeholder:text-[var(--text-muted)]"
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CaseEditor (inline add-case form)                                  */
/* ------------------------------------------------------------------ */

interface CaseEditorProps {
  suiteId: string;
  onSave: () => void;
  onCancel: () => void;
}

type EvalAssertionType =
  | "contains"
  | "not_contains"
  | "equals"
  | "regex"
  | "json_path"
  | "grounded"
  | "abstained"
  | "min_citations"
  | "latency_ms"
  | "agent_handoff"
  | "agent_isolation"
  | "budget_under"
  | "retry_used"
  | "fallback_used"
  | "no_schema_errors"
  | "no_guard_block";

interface AssertionDraft {
  type: EvalAssertionType;
  expected: string;
  field: string;
  path: string;
  fromAgent: string;
  toAgent: string;
  agentId: string;
  allowedTools: string;
  minCount: string;
}

const ASSERTION_OPTIONS: Array<{ value: EvalAssertionType; label: string }> = [
  { value: "contains", label: "Contains" },
  { value: "not_contains", label: "Not contains" },
  { value: "equals", label: "Equals" },
  { value: "regex", label: "Regex" },
  { value: "json_path", label: "JSON Path" },
  { value: "grounded", label: "Grounded" },
  { value: "abstained", label: "Abstained" },
  { value: "min_citations", label: "Min citations" },
  { value: "latency_ms", label: "Latency ms" },
  { value: "agent_handoff", label: "Agent handoff" },
  { value: "agent_isolation", label: "Agent isolation" },
  { value: "budget_under", label: "Budget under" },
  { value: "retry_used", label: "Retry used (v2.1)" },
  { value: "fallback_used", label: "Fallback used (v2.1)" },
  { value: "no_schema_errors", label: "No schema errors (v2.1)" },
  { value: "no_guard_block", label: "No guard block (v2.1)" },
];

function createAssertionDraft(): AssertionDraft {
  return {
    type: "contains",
    expected: "",
    field: "output",
    path: "",
    fromAgent: "",
    toAgent: "",
    agentId: "",
    allowedTools: "",
    minCount: "1",
  };
}

function buildAssertionPayload(draft: AssertionDraft): Record<string, unknown> {
  const payload: Record<string, unknown> = { type: draft.type };

  if (draft.field.trim()) payload.field = draft.field.trim();
  if (draft.path.trim()) payload.path = draft.path.trim();
  if (draft.fromAgent.trim()) payload.from_agent = draft.fromAgent.trim();
  if (draft.toAgent.trim()) payload.to_agent = draft.toAgent.trim();
  if (draft.agentId.trim()) payload.agent_id = draft.agentId.trim();

  if (draft.type === "agent_isolation") {
    payload.allowed_tools = draft.allowedTools
      .split(",")
      .map((tool) => tool.trim())
      .filter(Boolean);
  }

  if (draft.type === "retry_used") {
    const minCount = Number.parseInt(draft.minCount, 10);
    payload.min_count = Number.isNaN(minCount) ? 1 : Math.max(minCount, 1);
  }

  const requiresExpected =
    draft.type !== "grounded" &&
    draft.type !== "abstained" &&
    draft.type !== "budget_under" &&
    draft.type !== "no_schema_errors" &&
    draft.type !== "no_guard_block" &&
    draft.type !== "fallback_used" &&
    draft.type !== "retry_used" &&
    draft.type !== "agent_handoff" &&
    draft.type !== "agent_isolation";

  if (requiresExpected) {
    if (draft.type === "min_citations" || draft.type === "latency_ms") {
      const n = Number(draft.expected);
      payload.expected = Number.isNaN(n) ? draft.expected : n;
    } else {
      payload.expected = draft.expected;
    }
  }

  return payload;
}

function CaseEditor({ suiteId, onSave, onCancel }: CaseEditorProps) {
  const [name, setName] = useState("");
  const [inputJson, setInputJson] = useState('{\n  "text": ""\n}');
  const [tags, setTags] = useState<string[]>([]);
  const [assertions, setAssertions] = useState<AssertionDraft[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const handleSave = useCallback(async () => {
    if (!name.trim()) {
      toast.error("Case name is required");
      return;
    }

    let parsedInput: Record<string, unknown>;
    try {
      parsedInput = JSON.parse(inputJson);
    } catch {
      setJsonError("Invalid JSON");
      return;
    }
    setJsonError(null);

    setIsLoading(true);
    try {
      await api.createCase(suiteId, {
        name: name.trim(),
        input: parsedInput,
        assertions: assertions.map(buildAssertionPayload),
        tags: tags.length > 0 ? tags : undefined,
      });
      toast.success("Case created");
      onSave();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create case");
    } finally {
      setIsLoading(false);
    }
  }, [suiteId, name, inputJson, tags, assertions, onSave]);

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
          Case Name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="input-field w-full"
          placeholder="e.g., Should handle greeting properly"
          autoFocus
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
          Input Payload (JSON)
        </label>
        <textarea
          value={inputJson}
          onChange={(e) => {
            setInputJson(e.target.value);
            setJsonError(null);
          }}
          className={`input-field w-full min-h-[120px] resize-y font-mono text-xs ${
            jsonError ? "border-red-500" : ""
          }`}
          placeholder='{ "text": "Hello, how are you?" }'
        />
        {jsonError && (
          <p className="text-xs text-red-400 mt-1">{jsonError}</p>
        )}
      </div>

      <div>
        <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
          Tags (press Enter to add)
        </label>
        <ChipsInput
          value={tags}
          onChange={setTags}
          placeholder="Add tags…"
        />
      </div>

            <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-medium text-[var(--text-secondary)]">
            Assertions
          </label>
          <button
            type="button"
            onClick={() => setAssertions((prev) => [...prev, createAssertionDraft()])}
            className="btn-secondary text-xs px-2 py-1"
          >
            + Add assertion
          </button>
        </div>
        {assertions.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">
            Optional. Add checks for output, handoffs, retry/fallback, schema, and guard events.
          </p>
        ) : (
          <div className="space-y-2">
            {assertions.map((assertion, index) => (
              <div
                key={index}
                className="rounded-lg border p-2.5 space-y-2"
                style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
              >
                <div className="flex items-center gap-2">
                  <select
                    value={assertion.type}
                    onChange={(e) =>
                      setAssertions((prev) =>
                        prev.map((item, i) =>
                          i === index ? { ...item, type: e.target.value as EvalAssertionType } : item
                        )
                      )
                    }
                    className="input-field flex-1 text-xs"
                  >
                    {ASSERTION_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => setAssertions((prev) => prev.filter((_, i) => i !== index))}
                    className="btn-secondary text-xs px-2 py-1"
                  >
                    Remove
                  </button>
                </div>

                {(assertion.type === "contains" ||
                  assertion.type === "not_contains" ||
                  assertion.type === "equals" ||
                  assertion.type === "regex" ||
                  assertion.type === "min_citations" ||
                  assertion.type === "latency_ms") && (
                  <input
                    type="text"
                    value={assertion.expected}
                    onChange={(e) =>
                      setAssertions((prev) =>
                        prev.map((item, i) => (i === index ? { ...item, expected: e.target.value } : item))
                      )
                    }
                    className="input-field w-full text-xs"
                    placeholder="expected value"
                  />
                )}

                {assertion.type === "json_path" && (
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={assertion.path}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, path: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="path (e.g. output.score)"
                    />
                    <input
                      type="text"
                      value={assertion.expected}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, expected: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="expected"
                    />
                  </div>
                )}

                {assertion.type === "agent_handoff" && (
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={assertion.fromAgent}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, fromAgent: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="from agent id"
                    />
                    <input
                      type="text"
                      value={assertion.toAgent}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, toAgent: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="to agent id"
                    />
                  </div>
                )}

                {assertion.type === "agent_isolation" && (
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={assertion.agentId}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, agentId: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="agent id"
                    />
                    <input
                      type="text"
                      value={assertion.allowedTools}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, allowedTools: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="allowed tools (comma separated)"
                    />
                  </div>
                )}

                {assertion.type === "retry_used" && (
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={assertion.agentId}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, agentId: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="agent id (optional)"
                    />
                    <input
                      type="number"
                      min={1}
                      value={assertion.minCount}
                      onChange={(e) =>
                        setAssertions((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, minCount: e.target.value } : item))
                        )
                      }
                      className="input-field text-xs"
                      placeholder="min count"
                    />
                  </div>
                )}

                {assertion.type === "fallback_used" && (
                  <input
                    type="text"
                    value={assertion.agentId}
                    onChange={(e) =>
                      setAssertions((prev) =>
                        prev.map((item, i) => (i === index ? { ...item, agentId: e.target.value } : item))
                      )
                    }
                    className="input-field w-full text-xs"
                    placeholder="agent id (optional)"
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
<div className="flex gap-2 pt-2">
        <button onClick={onCancel} className="btn-secondary flex-1" disabled={isLoading}>
          Cancel
        </button>
        <button onClick={handleSave} className="btn-pill flex-1" disabled={isLoading}>
          {isLoading ? "Creating…" : "Add Case"}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main editor component                                             */
/* ------------------------------------------------------------------ */

export default function EvalSuiteEditor({ suiteId, cases, onCasesChanged }: EvalSuiteEditorProps) {
  const [showAddCase, setShowAddCase] = useState(false);

  const handleCaseSaved = () => {
    setShowAddCase(false);
    onCasesChanged();
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-[var(--text-secondary)]">
          Test Cases
        </h4>
        <button
          onClick={() => setShowAddCase(true)}
          className="btn-pill text-sm"
          disabled={showAddCase}
        >
          <span className="flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Case
          </span>
        </button>
      </div>

      {/* Inline case editor */}
      {showAddCase && (
        <div
          className="rounded-xl p-4 border"
          style={{
            backgroundColor: "var(--bg-tertiary)",
            borderColor: "var(--border-default)",
          }}
        >
          <CaseEditor
            suiteId={suiteId}
            onSave={handleCaseSaved}
            onCancel={() => setShowAddCase(false)}
          />
        </div>
      )}

      {/* Cases list */}
      {cases.length === 0 && !showAddCase ? (
        <div className="text-center py-8 text-[var(--text-muted)]">
          <p>No test cases yet. Add your first case above.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {cases.map((testCase) => (
            <CaseCard key={testCase.id} testCase={testCase} onChanged={onCasesChanged} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CaseCard (read-only display of a case)                            */
/* ------------------------------------------------------------------ */

function CaseCard({ testCase, onChanged }: { testCase: EvalCase; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editName, setEditName] = useState(testCase.name);
  const [editInput, setEditInput] = useState(JSON.stringify(testCase.input, null, 2));
  const [editExpected, setEditExpected] = useState(JSON.stringify(testCase.expected ?? {}, null, 2));
  const [editAssertions, setEditAssertions] = useState(JSON.stringify(testCase.assertions ?? [], null, 2));

  const inputSummary = (() => {
    try {
      // Show a one-line summary of the input
      const text = testCase.input?.text;
      if (typeof text === "string") return text;
      return JSON.stringify(testCase.input).slice(0, 120);
    } catch {
      return "—";
    }
  })();

  const assertionSummary = (assertion: Record<string, unknown>) => {
    const type = String(assertion.type ?? "unknown");
    const expected = assertion.expected;
    const fromAgent = assertion.from_agent;
    const toAgent = assertion.to_agent;
    const agentId = assertion.agent_id;
    const minCount = assertion.min_count;

    if (type === "agent_handoff") {
      return `${String(fromAgent ?? "?")} -> ${String(toAgent ?? "?")}`;
    }
    if (type === "agent_isolation") {
      const allowed = Array.isArray(assertion.allowed_tools)
        ? (assertion.allowed_tools as unknown[]).map(String).join(", ")
        : "";
      return `agent=${String(agentId ?? "?")} tools=[${allowed}]`;
    }
    if (type === "retry_used") {
      return `agent=${String(agentId ?? "any")} min=${String(minCount ?? 1)}`;
    }
    if (type === "fallback_used") {
      return `agent=${String(agentId ?? "any")}`;
    }
    if (expected != null) {
      return `expected=${String(expected)}`;
    }
    return "";
  };

  return (
    <div
      className="rounded-xl border transition-all hover:border-[var(--text-muted)]"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-default)",
      }}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        className="w-full p-4 text-left"
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-medium text-white truncate">{testCase.name}</h4>
            <p className="text-xs text-[var(--text-muted)] mt-1 line-clamp-2">
              {inputSummary}
            </p>

            {/* Tags */}
            {testCase.tags && testCase.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {testCase.tags.map((tag, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 text-[10px] rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {/* Assertions count */}
            {testCase.assertions && testCase.assertions.length > 0 && (
              <span className="inline-block mt-2 px-2 py-0.5 text-[10px] rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                {testCase.assertions.length} assertion{testCase.assertions.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 ml-3 flex-shrink-0">
            <button
              type="button"
              className="btn-secondary text-xs px-2 py-1"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded(true);
                setEditing((v) => !v);
              }}
            >
              {editing ? "Close" : "Edit"}
            </button>
            <button
              type="button"
              className="btn-secondary text-xs px-2 py-1"
              style={{ color: "#f87171" }}
              onClick={async (e) => {
                e.stopPropagation();
                if (!confirm("Delete this case?")) return;
                try {
                  await api.deleteCase(testCase.id);
                  toast.success("Case deleted");
                  onChanged();
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Failed to delete case");
                }
              }}
            >
              Del
            </button>
            <svg
              className={`w-4 h-4 text-[var(--text-muted)] transition-transform ${
                expanded ? "rotate-180" : ""
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-[var(--border-default)]">
          <div className="space-y-3">
            {editing && (
              <div
                className="space-y-3 rounded-lg border p-3"
                style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-tertiary)" }}
              >
                <div>
                  <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">Name</label>
                  <input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="input-field w-full text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">Input JSON</label>
                  <textarea
                    value={editInput}
                    onChange={(e) => setEditInput(e.target.value)}
                    className="input-field w-full min-h-[80px] text-xs font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">Expected JSON</label>
                  <textarea
                    value={editExpected}
                    onChange={(e) => setEditExpected(e.target.value)}
                    className="input-field w-full min-h-[70px] text-xs font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">Assertions JSON</label>
                  <textarea
                    value={editAssertions}
                    onChange={(e) => setEditAssertions(e.target.value)}
                    className="input-field w-full min-h-[100px] text-xs font-mono"
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    className="btn-secondary text-xs"
                    onClick={() => {
                      setEditName(testCase.name);
                      setEditInput(JSON.stringify(testCase.input, null, 2));
                      setEditExpected(JSON.stringify(testCase.expected ?? {}, null, 2));
                      setEditAssertions(JSON.stringify(testCase.assertions ?? [], null, 2));
                      setEditing(false);
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn-pill text-xs"
                    disabled={saving}
                    onClick={async () => {
                      let parsedInput: Record<string, unknown>;
                      let parsedExpected: Record<string, unknown>;
                      let parsedAssertions: Record<string, unknown>[];
                      try {
                        parsedInput = JSON.parse(editInput || "{}");
                        parsedExpected = JSON.parse(editExpected || "{}");
                        parsedAssertions = JSON.parse(editAssertions || "[]");
                        if (!Array.isArray(parsedAssertions)) {
                          throw new Error("Assertions must be an array");
                        }
                      } catch (err) {
                        toast.error(err instanceof Error ? err.message : "Invalid JSON");
                        return;
                      }
                      setSaving(true);
                      try {
                        await api.updateCase(testCase.id, {
                          name: editName.trim() || testCase.name,
                          input: parsedInput,
                          expected: parsedExpected,
                          assertions: parsedAssertions,
                        });
                        toast.success("Case updated");
                        setEditing(false);
                        onChanged();
                      } catch (err) {
                        toast.error(err instanceof Error ? err.message : "Failed to update case");
                      } finally {
                        setSaving(false);
                      }
                    }}
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">Input</label>
              <pre className="text-xs text-[var(--text-secondary)] bg-[var(--bg-primary)] rounded-md p-2 overflow-x-auto max-h-40">
                {JSON.stringify(testCase.input, null, 2)}
              </pre>
            </div>

            {testCase.expected && Object.keys(testCase.expected).length > 0 && (
              <div>
                <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">Expected</label>
                <pre className="text-xs text-[var(--text-secondary)] bg-[var(--bg-primary)] rounded-md p-2 overflow-x-auto max-h-40">
                  {JSON.stringify(testCase.expected, null, 2)}
                </pre>
              </div>
            )}

            {testCase.assertions && testCase.assertions.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">Assertions</label>
                <div className="space-y-2">
                  {(testCase.assertions as Record<string, unknown>[]).map((assertion, index) => (
                    <div
                      key={index}
                      className="rounded-md p-2 border"
                      style={{ backgroundColor: "var(--bg-primary)", borderColor: "var(--border-default)" }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] uppercase tracking-wide text-violet-300">
                          {String(assertion.type ?? "unknown")}
                        </span>
                        <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                          {assertionSummary(assertion)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="text-xs text-[var(--text-muted)]">
              Created {new Date(testCase.created_at).toLocaleString()}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

