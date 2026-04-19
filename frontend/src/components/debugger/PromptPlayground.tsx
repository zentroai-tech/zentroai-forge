"use client";

import { useState, useCallback, useEffect } from "react";
import toast from "react-hot-toast";
import { getFlow } from "@/lib/api";
import type { FlowNode } from "@/types/ir";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface PromptPlaygroundProps {
  flowId: string;
  onClose: () => void;
  embedded?: boolean;
}

export default function PromptPlayground({ flowId, onClose, embedded }: PromptPlaygroundProps) {
  const [llmNodes, setLlmNodes] = useState<FlowNode[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [variablesJson, setVariablesJson] = useState('{\n  "input": "Hello"\n}');
  const [modelOverride, setModelOverride] = useState("");
  const [temperatureOverride, setTemperatureOverride] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [loadingFlow, setLoadingFlow] = useState(true);
  const [result, setResult] = useState<{
    rendered_prompt?: string;
    rendered_system_prompt?: string | null;
    output?: unknown;
    error?: string;
    status: string;
    model?: string;
    temperature?: number;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingFlow(true);
    getFlow(flowId)
      .then((flow) => {
        if (cancelled) return;
        const llm = (flow.nodes || []).filter((n) => n.type === "LLM");
        setLlmNodes(llm);
        if (llm.length > 0) {
          setSelectedNodeId((current) => current || llm[0].id);
        }
      })
      .catch(() => toast.error("Failed to load flow"))
      .finally(() => {
        if (!cancelled) setLoadingFlow(false);
      });
    return () => { cancelled = true; };
  }, [flowId]);

  const handleTest = useCallback(async () => {
    if (!selectedNodeId) {
      toast.error("Select an LLM node");
      return;
    }
    let variables: Record<string, unknown> = {};
    try {
      variables = JSON.parse(variablesJson);
    } catch {
      toast.error("Invalid JSON for variables");
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      const body: { variables: Record<string, unknown>; model_override?: string; temperature_override?: number } = {
        variables,
      };
      if (modelOverride.trim()) body.model_override = modelOverride.trim();
      const t = parseFloat(temperatureOverride);
      if (!Number.isNaN(t)) body.temperature_override = t;

      const res = await fetch(
        `${API_BASE}/debug/flows/${flowId}/nodes/${selectedNodeId}/test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      const data = await res.json();
      setResult({
        rendered_prompt: data.rendered_prompt,
        rendered_system_prompt: data.rendered_system_prompt ?? null,
        output: data.output,
        error: data.error,
        status: data.status ?? (data.error ? "failed" : "success"),
        model: data.model,
        temperature: data.temperature,
      });
      if (data.status === "failed" && data.error) toast.error(data.error);
      else toast.success("Prompt test completed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Request failed");
      setResult({ status: "failed", error: String(e) });
    } finally {
      setLoading(false);
    }
  }, [flowId, selectedNodeId, variablesJson, modelOverride, temperatureOverride]);

  const outputText =
    result?.output != null && typeof result.output === "object" && "output" in result.output
      ? String((result.output as { output?: unknown }).output ?? "")
      : result?.output != null
        ? (typeof result.output === "string" ? result.output : JSON.stringify(result.output, null, 2))
        : "";

  const outputIsObject = result?.output != null && typeof result.output === "object";

  const contentBody = (
    <div className="flex-1 flex overflow-hidden min-h-0">
          {/* Left: Config */}
          <div
            className="w-80 flex-shrink-0 flex flex-col border-r overflow-hidden"
            style={{ borderColor: "var(--border-default)" }}
          >
            <div className="p-3 border-b" style={{ borderColor: "var(--border-default)" }}>
              <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                Configuration
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-4">
              {loadingFlow ? (
                <p className="text-sm text-[var(--text-muted)]">Loading...</p>
              ) : llmNodes.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">
                  This flow has no LLM nodes. Add an LLM node to test prompts.
                </p>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-muted)" }}>
                      LLM Node
                    </label>
                    <select
                      value={selectedNodeId ?? ""}
                      onChange={(e) => setSelectedNodeId(e.target.value || null)}
                      className="w-full rounded-lg px-3 py-2 text-sm"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        border: "1px solid var(--border-default)",
                        color: "var(--text-primary)",
                      }}
                    >
                      {llmNodes.map((n) => (
                        <option key={n.id} value={n.id}>
                          {n.id}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-muted)" }}>
                      Variables (JSON)
                    </label>
                    <textarea
                      value={variablesJson}
                      onChange={(e) => setVariablesJson(e.target.value)}
                      placeholder='{"input": "Hello"}'
                      rows={6}
                      className="w-full rounded-lg px-3 py-2 text-xs font-mono resize-none"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        border: "1px solid var(--border-default)",
                        color: "var(--text-primary)",
                      }}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>
                        Model
                      </label>
                      <input
                        type="text"
                        value={modelOverride}
                        onChange={(e) => setModelOverride(e.target.value)}
                        placeholder="Optional"
                        className="w-full rounded-lg px-2 py-1.5 text-xs"
                        style={{
                          backgroundColor: "var(--bg-tertiary)",
                          border: "1px solid var(--border-default)",
                          color: "var(--text-primary)",
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>
                        Temperature
                      </label>
                      <input
                        type="text"
                        value={temperatureOverride}
                        onChange={(e) => setTemperatureOverride(e.target.value)}
                        placeholder="Optional"
                        className="w-full rounded-lg px-2 py-1.5 text-xs"
                        style={{
                          backgroundColor: "var(--bg-tertiary)",
                          border: "1px solid var(--border-default)",
                          color: "var(--text-primary)",
                        }}
                      />
                    </div>
                  </div>

                  <button
                    onClick={handleTest}
                    disabled={loading}
                    className="w-full btn-pill py-2.5 !text-sm"
                    style={{
                      opacity: loading ? 0.5 : 1,
                    }}
                  >
                    {loading ? "Running..." : "Test Prompt"}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Right: Result */}
          <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: "var(--bg-primary)" }}>
            <div className="p-3 border-b flex items-center justify-between" style={{ borderColor: "var(--border-default)" }}>
              <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                Result
              </span>
              {result && (
                <span
                  className="text-[10px] px-2 py-0.5 rounded-full"
                  style={{
                    backgroundColor: result.status === "success" ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                    color: result.status === "success" ? "#22c55e" : "#ef4444",
                  }}
                >
                  {result.status}
                </span>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {!result && !loading && (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    Select a node, set variables, and click <strong className="text-[var(--text-primary)]">Test Prompt</strong> to see rendered prompts and LLM output here.
                  </p>
                </div>
              )}

              {result && (
                <>
                  {result.rendered_system_prompt != null && result.rendered_system_prompt !== "" && (
                    <div
                      className="rounded-lg border p-3"
                      style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
                    >
                      <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>
                        System prompt
                      </h3>
                      <pre
                        className="text-xs whitespace-pre-wrap break-words p-3 rounded max-h-40 overflow-auto font-mono"
                        style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                      >
                        {result.rendered_system_prompt}
                      </pre>
                    </div>
                  )}

                  {result.rendered_prompt != null && (
                    <div
                      className="rounded-lg border p-3"
                      style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
                    >
                      <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>
                        User prompt
                      </h3>
                      <pre
                        className="text-xs whitespace-pre-wrap break-words p-3 rounded max-h-40 overflow-auto font-mono"
                        style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                      >
                        {result.rendered_prompt}
                      </pre>
                    </div>
                  )}

                  {result.status === "success" && (outputText || outputIsObject) && (
                    <div
                      className="rounded-lg border p-3"
                      style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-secondary)" }}
                    >
                      <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>
                        Output
                      </h3>
                      <pre
                        className="text-xs whitespace-pre-wrap break-words p-3 rounded max-h-64 overflow-auto font-mono"
                        style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                      >
                        {outputIsObject && typeof result.output === "object" && result.output !== null && !("output" in result.output)
                          ? JSON.stringify(result.output, null, 2)
                          : outputText}
                      </pre>
                      {outputIsObject && typeof result.output === "object" && result.output !== null && "output" in result.output && (
                        <details className="mt-2">
                          <summary className="text-xs cursor-pointer" style={{ color: "var(--text-muted)" }}>
                            Full response (JSON)
                          </summary>
                          <pre
                            className="mt-2 text-[10px] p-2 rounded overflow-auto max-h-32 font-mono"
                            style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                          >
                            {JSON.stringify(result.output, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  )}

                  {result.error && (
                    <div
                      className="rounded-lg border p-3 text-sm text-red-400"
                      style={{
                        borderColor: "rgba(239, 68, 68, 0.3)",
                        backgroundColor: "rgba(239, 68, 68, 0.1)",
                      }}
                    >
                      {result.error}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
  );

  if (embedded) return <div className="h-full flex flex-col">{contentBody}</div>;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-5xl mx-4 h-[85vh] flex flex-col border"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between flex-shrink-0"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Prompt Playground</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-muted)" }}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {contentBody}
      </div>
    </div>
  );
}
