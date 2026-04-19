/**
 * Types for Eval Suites — aligned with the backend Pydantic models
 * (routers/evals.py).
 *
 * NOTE: There are NO PUT/PATCH endpoints. Suites and cases are
 *       create-only / delete-only.
 */

/* ------------------------------------------------------------------ */
/*  Suite                                                             */
/* ------------------------------------------------------------------ */

/** Full suite as returned by GET /evals/suites/{id} */
export interface EvalSuite {
  id: string;
  flow_id: string;
  name: string;
  description: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/**
 * List item returned by GET /evals/flows/{flow_id}/suites.
 * The backend returns the same shape as EvalSuite (no case_count).
 */
export type EvalSuiteListItem = EvalSuite;

/* ------------------------------------------------------------------ */
/*  Case                                                              */
/* ------------------------------------------------------------------ */

/** Case as returned by GET /evals/suites/{suite_id}/cases */
export interface EvalCase {
  id: string;
  suite_id: string;
  name: string;
  description: string;
  input: Record<string, unknown>;
  expected: Record<string, unknown>;
  assertions: Record<string, unknown>[];
  tags: string[];
  created_at: string;
}

/* ------------------------------------------------------------------ */
/*  Runs & Results                                                    */
/* ------------------------------------------------------------------ */

/** Run as returned by POST /evals/suites/{id}/run or GET /evals/runs/{id} */
export interface EvalRun {
  id: string;
  suite_id: string;
  status: "pending" | "running" | "completed" | "failed";
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  /** null until run completes; true = thresholds met, false = gate failed */
  gate_passed: boolean | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

/** Individual case result within a run */
export interface EvalCaseResult {
  id: string;
  case_id: string;
  run_id: string | null;
  status: string;
  assertions: Record<string, unknown>[];
  error_message: string | null;
  duration_ms: number | null;
}

/* ------------------------------------------------------------------ */
/*  Payloads                                                          */
/* ------------------------------------------------------------------ */

export interface CreateEvalSuitePayload {
  name: string;
  description?: string;
  config?: Record<string, unknown>;
}

export interface CreateEvalCasePayload {
  name: string;
  description?: string;
  input: Record<string, unknown>;
  expected?: Record<string, unknown>;
  assertions?: Record<string, unknown>[];
  tags?: string[];
}

export interface UpdateEvalCasePayload {
  name?: string;
  description?: string;
  input?: Record<string, unknown>;
  expected?: Record<string, unknown>;
  assertions?: Record<string, unknown>[];
  tags?: string[];
}

export interface RunSuitePayload {
  tags?: string[];
}

/* ------------------------------------------------------------------ */
/*  Legacy compat aliases (kept so old imports don't break elsewhere)  */
/* ------------------------------------------------------------------ */

/** @deprecated Use EvalRun instead */
export type EvalSuiteRunResult = EvalRun;

/** @deprecated No longer used — assertions stored as generic dicts */
export interface EvalAssertion {
  must_abstain?: boolean;
  must_cite?: boolean;
  min_top_score?: number;
  must_include?: string[];
  must_not_include?: string[];
}
