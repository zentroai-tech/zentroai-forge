/**
 * Hook for consuming SSE-streamed flow executions.
 *
 * Usage:
 *   const { events, isStreaming, startStream } = useStreamRun();
 *   startStream(flowId, input);
 */

import { useState, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface StreamEvent {
  type: "step_started" | "step_completed" | "step_failed" | "run_completed" | "run_failed" | "run_detail" | "error";
  run_id?: string;
  node_id?: string;
  node_type?: string;
  order?: number;
  output?: unknown;
  duration_ms?: number;
  status?: string;
  error?: string;
  payload?: unknown;
}

export function useStreamRun() {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startStream = useCallback(async (flowId: string, input: Record<string, unknown>) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setEvents([]);
    setRunId(null);
    setIsStreaming(true);

    try {
      const res = await fetch(`${API_BASE}/flows/${flowId}/runs/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input }),
        signal: ctrl.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(typeof err.detail === "string" ? err.detail : "Stream failed");
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        setIsStreaming(false);
        return;
      }

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]" || data.trim() === "") continue;
            try {
              const parsed = JSON.parse(data) as { event?: string; [k: string]: unknown };
              const eventType = (parsed.event ?? parsed.type) as string;
              const ev: StreamEvent = {
                type: eventType as StreamEvent["type"],
                run_id: parsed.run_id as string,
                node_id: parsed.node_id as string,
                node_type: parsed.node_type as string,
                order: parsed.order as number,
                output: parsed.output,
                duration_ms: parsed.duration_ms as number,
                status: parsed.status as string,
                error: parsed.error as string,
                payload: parsed,
              };
              if (ev.run_id) setRunId(ev.run_id);
              setEvents((prev) => [...prev, ev]);
            } catch {
              // skip malformed
            }
          }
        }
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setEvents((prev) => [...prev, { type: "error", error: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }, []);

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setRunId(null);
  }, []);

  return { events, isStreaming, runId, startStream, stopStream, clearEvents };
}
