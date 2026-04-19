export type RuntimeRunStatus = "running" | "completed" | "failed" | string;

export interface RuntimeRunCreateRequest {
  entrypoint?: string;
  input: Record<string, unknown>;
}

export interface RuntimeRunSummary {
  run_id: string;
  trace_id?: string;
  session_id?: string;
  entrypoint?: string;
  status: RuntimeRunStatus;
  replay_of?: string;
  result?: Record<string, unknown>;
}

export interface RuntimeRunStep {
  step_id: string;
  status: string;
  node_type?: string;
  tool_name?: string;
  replay_substituted?: boolean;
  input?: unknown;
  output?: unknown;
}

export interface RuntimeToolSpec {
  name: string;
  description: string;
  adapter: string;
  timeout_s: number;
  max_retries: number;
  requires_approval: boolean;
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
}

export interface ApprovalRequest {
  approval_id: string;
  tool_name: string;
  scope: string;
  status: "pending" | "approved" | "denied" | string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface ReplayRunResponse {
  replay_run_id: string;
  status: string;
}

export interface ToolHealth {
  tools: Record<
    string,
    {
      rate_limit: { last_ts: number; allowed: number; denied: number };
      circuit: {
        open: boolean;
        failures: number;
        opened_at: number;
        cooldown_s: number;
        remaining_cooldown_s: number;
      };
    }
  >;
}

export interface SessionMemorySnapshot {
  session_id: string;
  summary: unknown[];
  raw_count: number;
}

const RUNTIME_API_BASE =
  process.env.NEXT_PUBLIC_RUNTIME_API_BASE?.trim() || "http://localhost:9090";

async function runtimeFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${RUNTIME_API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const payload = (await res.json()) as Record<string, unknown>;
      if (typeof payload.message === "string") message = payload.message;
      else if (typeof payload.error === "string") message = payload.error;
    } catch {
      // ignore parse errors
    }
    throw new Error(message);
  }

  return (await res.json()) as T;
}

export async function createRuntimeRun(
  payload: RuntimeRunCreateRequest
): Promise<RuntimeRunSummary> {
  const raw = await runtimeFetch<Record<string, unknown>>("/runs", {
    method: "POST",
    body: JSON.stringify({
      entrypoint: payload.entrypoint || "main",
      input: payload.input || {},
    }),
  });
  const nested = (raw.result || {}) as Record<string, unknown>;
  const runId =
    String(raw.run_id || nested.run_id || raw.id || "").trim();
  if (!runId) {
    throw new Error(
      `runtime_returned_empty_run_id payload=${JSON.stringify(raw).slice(0, 500)}`
    );
  }
  return {
    run_id: runId,
    trace_id: String(raw.trace_id || nested.trace_id || "").trim() || undefined,
    session_id: String(raw.session_id || nested.session_id || "").trim() || undefined,
    entrypoint: String(raw.entrypoint || "").trim() || undefined,
    status: String(raw.status || "completed"),
    replay_of: String(raw.replay_of || "").trim() || undefined,
    result: (raw.result as Record<string, unknown>) || {},
  };
}

export async function getRuntimeRun(runId: string): Promise<RuntimeRunSummary> {
  if (!runId?.trim()) {
    throw new Error("run_id_required");
  }
  return runtimeFetch<RuntimeRunSummary>(`/runs/${encodeURIComponent(runId)}`);
}

export async function getRuntimeRunSteps(runId: string): Promise<RuntimeRunStep[]> {
  if (!runId?.trim()) {
    throw new Error("run_id_required");
  }
  const payload = await runtimeFetch<{ run_id: string; steps: RuntimeRunStep[]; replay_of?: string | null }>(
    `/runs/${encodeURIComponent(runId)}/steps`
  );
  return payload.steps || [];
}

export async function listRuntimeTools(): Promise<RuntimeToolSpec[]> {
  const payload = await runtimeFetch<{ tools: RuntimeToolSpec[] }>("/tools");
  return payload.tools || [];
}

export async function getRuntimeSessionState(
  sessionId: string
): Promise<Record<string, unknown>> {
  const payload = await runtimeFetch<{ session_id: string; state: Record<string, unknown> }>(
    `/state/${encodeURIComponent(sessionId)}`
  );
  return payload.state || {};
}

export async function pingRuntimeHealth(): Promise<{
  ok: boolean;
  status: string;
}> {
  try {
    const payload = await runtimeFetch<{ status?: string }>("/healthz");
    return { ok: true, status: payload.status || "ok" };
  } catch {
    return { ok: false, status: "unreachable" };
  }
}

export async function requestApproval(payload: {
  tool_name: string;
  scope?: string;
  metadata?: Record<string, unknown>;
}): Promise<{ approval_id: string; status: string }> {
  return runtimeFetch("/approvals/request", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function approveRequest(approvalId: string): Promise<{ approval_id: string; status: string }> {
  return runtimeFetch(`/approvals/${encodeURIComponent(approvalId)}/approve`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function denyRequest(approvalId: string): Promise<{ approval_id: string; status: string }> {
  return runtimeFetch(`/approvals/${encodeURIComponent(approvalId)}/deny`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function listApprovals(params?: {
  status?: string;
  session_id?: string;
}): Promise<ApprovalRequest[]> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.session_id) q.set("session_id", params.session_id);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  const payload = await runtimeFetch<{ items: ApprovalRequest[] }>(`/approvals${suffix}`);
  return payload.items || [];
}

export async function getApproval(approvalId: string): Promise<ApprovalRequest> {
  return runtimeFetch<ApprovalRequest>(`/approvals/${encodeURIComponent(approvalId)}`);
}

export async function replayRun(payload: { run_id: string; mode?: "play" }): Promise<ReplayRunResponse> {
  return runtimeFetch<ReplayRunResponse>("/replay", {
    method: "POST",
    body: JSON.stringify({ run_id: payload.run_id, mode: payload.mode || "play" }),
  });
}

export async function getRunArtifacts(runId: string): Promise<string[]> {
  const payload = await runtimeFetch<{ run_id: string; artifacts: string[] }>(
    `/runs/${encodeURIComponent(runId)}/artifacts`
  );
  return payload.artifacts || [];
}

export async function getRunArtifact(runId: string, name: string): Promise<string> {
  const encodedName = name
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  const res = await fetch(
    `${RUNTIME_API_BASE}/runs/${encodeURIComponent(runId)}/artifacts/${encodedName}`,
    { cache: "no-store" }
  );
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.text();
}

export async function getToolsHealth(): Promise<ToolHealth> {
  return runtimeFetch<ToolHealth>("/tools/health");
}

export async function getSessionMemory(sessionId: string): Promise<SessionMemorySnapshot> {
  return runtimeFetch<SessionMemorySnapshot>(`/sessions/${encodeURIComponent(sessionId)}/memory`);
}

export async function summarizeSession(
  sessionId: string,
  maxItems: number = 50
): Promise<SessionMemorySnapshot> {
  return runtimeFetch<SessionMemorySnapshot>(`/sessions/${encodeURIComponent(sessionId)}/summarize`, {
    method: "POST",
    body: JSON.stringify({ max_items: maxItems }),
  });
}
