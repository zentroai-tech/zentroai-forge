/**
 * Eval Suites API client — wired to the real backend endpoints under /evals.
 *
 * Every function accepts an optional AbortSignal so callers can cancel
 * in-flight requests (e.g. when the modal unmounts).
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Types (aligned with backend Pydantic models)                      */
/* ------------------------------------------------------------------ */

import type {
  EvalSuite,
  EvalCase,
  EvalRun,
  EvalCaseResult,
  CreateEvalSuitePayload,
  CreateEvalCasePayload,
  UpdateEvalCasePayload,
  RunSuitePayload,
} from "@/types/eval";

/* ------------------------------------------------------------------ */
/*  Fetch helper                                                     */
/* ------------------------------------------------------------------ */

async function fetchEvals<T>(
  path: string,
  options: RequestInit & { signal?: AbortSignal } = {}
): Promise<T> {
  const { signal, ...rest } = options;
  const url = `${API_BASE}/evals${path}`;
  const res = await fetch(url, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(rest.headers as Record<string, string>),
    },
    signal: signal ?? undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/* ------------------------------------------------------------------ */
/*  Suites                                                            */
/* ------------------------------------------------------------------ */

export async function listSuites(
  flowId: string,
  limit = 50,
  offset = 0,
  signal?: AbortSignal
): Promise<EvalSuite[]> {
  return fetchEvals<EvalSuite[]>(
    `/flows/${encodeURIComponent(flowId)}/suites?limit=${limit}&offset=${offset}`,
    { signal }
  );
}

export async function getSuite(
  suiteId: string,
  signal?: AbortSignal
): Promise<EvalSuite> {
  return fetchEvals<EvalSuite>(`/suites/${encodeURIComponent(suiteId)}`, {
    signal,
  });
}

export async function createSuite(
  flowId: string,
  payload: CreateEvalSuitePayload,
  signal?: AbortSignal
): Promise<EvalSuite> {
  return fetchEvals<EvalSuite>(
    `/flows/${encodeURIComponent(flowId)}/suites`,
    {
      method: "POST",
      body: JSON.stringify({
        name: payload.name,
        description: payload.description ?? "",
        config: payload.config ?? {},
      }),
      signal,
    }
  );
}

export async function deleteSuite(
  suiteId: string,
  signal?: AbortSignal
): Promise<void> {
  await fetchEvals<void>(`/suites/${encodeURIComponent(suiteId)}`, {
    method: "DELETE",
    signal,
  });
}

/* ------------------------------------------------------------------ */
/*  Cases                                                             */
/* ------------------------------------------------------------------ */

export async function listCases(
  suiteId: string,
  signal?: AbortSignal
): Promise<EvalCase[]> {
  return fetchEvals<EvalCase[]>(
    `/suites/${encodeURIComponent(suiteId)}/cases`,
    { signal }
  );
}

export async function createCase(
  suiteId: string,
  payload: CreateEvalCasePayload,
  signal?: AbortSignal
): Promise<EvalCase> {
  return fetchEvals<EvalCase>(
    `/suites/${encodeURIComponent(suiteId)}/cases`,
    {
      method: "POST",
      body: JSON.stringify({
        name: payload.name,
        description: payload.description ?? "",
        input: payload.input,
        expected: payload.expected ?? {},
        assertions: payload.assertions ?? [],
        tags: payload.tags ?? [],
      }),
      signal,
    }
  );
}

export async function updateCase(
  caseId: string,
  payload: UpdateEvalCasePayload,
  signal?: AbortSignal
): Promise<EvalCase> {
  return fetchEvals<EvalCase>(
    `/cases/${encodeURIComponent(caseId)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export async function deleteCase(
  caseId: string,
  signal?: AbortSignal
): Promise<void> {
  await fetchEvals<void>(`/cases/${encodeURIComponent(caseId)}`, {
    method: "DELETE",
    signal,
  });
}

/* ------------------------------------------------------------------ */
/*  Runs & Results                                                     */
/* ------------------------------------------------------------------ */

export async function listRuns(
  suiteId: string,
  limit = 20,
  signal?: AbortSignal
): Promise<EvalRun[]> {
  return fetchEvals<EvalRun[]>(
    `/suites/${encodeURIComponent(suiteId)}/runs?limit=${limit}`,
    { signal }
  );
}

export async function runSuite(
  suiteId: string,
  payload?: RunSuitePayload,
  signal?: AbortSignal
): Promise<EvalRun> {
  return fetchEvals<EvalRun>(
    `/suites/${encodeURIComponent(suiteId)}/run`,
    {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
      signal,
    }
  );
}

export async function getRun(
  runId: string,
  signal?: AbortSignal
): Promise<EvalRun> {
  return fetchEvals<EvalRun>(`/runs/${encodeURIComponent(runId)}`, {
    signal,
  });
}

export async function getRunResults(
  runId: string,
  signal?: AbortSignal
): Promise<EvalCaseResult[]> {
  return fetchEvals<EvalCaseResult[]>(
    `/runs/${encodeURIComponent(runId)}/results`,
    { signal }
  );
}

export async function downloadReport(runId: string): Promise<Blob> {
  const url = `${API_BASE}/evals/runs/${encodeURIComponent(runId)}/report`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to download report: ${res.statusText}`);
  return res.blob();
}

export interface DatasetImportResult {
  suite_id: string;
  imported_cases: number;
  case_ids: string[];
}

export async function uploadDataset(
  suiteId: string,
  file: File,
  signal?: AbortSignal
): Promise<DatasetImportResult> {
  const form = new FormData();
  form.append("file", file);
  const url = `${API_BASE}/evals/suites/${encodeURIComponent(suiteId)}/dataset`;
  const res = await fetch(url, { method: "POST", body: form, signal });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<DatasetImportResult>;
}
