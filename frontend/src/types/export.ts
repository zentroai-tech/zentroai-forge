/**
 * Types for the export/code preview API
 */

// ── Legacy preset type (kept for backward compat) ─────────────────────────
export type ExportTarget = "langgraph" | "runtime" | "api_server" | "aws-ecs";

// ── Composable dimensions ──────────────────────────────────────────────────
export type ExportEngine = "dispatcher" | "langgraph";
export type ExportSurface = "cli" | "http";
export type ExportPackaging = "local" | "aws-ecs";

/** Full composable export configuration sent to the backend. */
export interface ExportConfig {
  engine: ExportEngine;
  surface: ExportSurface;
  packaging: ExportPackaging;
  /** True when user customised via the Advanced popover */
  isAdvanced: boolean;
}

/** Preset definition (the 4 standard targets) */
export interface ExportPreset {
  id: ExportTarget;
  label: string;
  description: string;
  recommended?: boolean;
  config: Omit<ExportConfig, "isAdvanced">;
}

export const EXPORT_PRESETS: ExportPreset[] = [
  {
    id: "langgraph",
    label: "LangGraph",
    description: "Production-ready agent with LangGraph orchestration",
    recommended: true,
    config: { engine: "langgraph", surface: "cli", packaging: "local" },
  },
  {
    id: "runtime",
    label: "Simple Runtime",
    description: "Lightweight dispatcher, minimal dependencies",
    config: { engine: "dispatcher", surface: "cli", packaging: "local" },
  },
  {
    id: "api_server",
    label: "API Server",
    description: "FastAPI server — /health, /healthz, /metrics, /run + Docker",
    config: { engine: "dispatcher", surface: "http", packaging: "local" },
  },
  {
    id: "aws-ecs",
    label: "AWS ECS (Fargate)",
    description: "Terraform infra + Secrets Manager + CloudWatch",
    config: { engine: "dispatcher", surface: "http", packaging: "aws-ecs" },
  },
];

/** Kept for legacy code that imports EXPORT_TARGETS */
export interface ExportTargetOption {
  value: ExportTarget;
  label: string;
  description: string;
  recommended?: boolean;
}
export const EXPORT_TARGETS: ExportTargetOption[] = EXPORT_PRESETS.map((p) => ({
  value: p.id,
  label: p.label,
  description: p.description,
  recommended: p.recommended,
}));

/** Build a human-readable label from an ExportConfig */
export function exportConfigLabel(cfg: ExportConfig): string {
  if (cfg.packaging === "aws-ecs") {
    const eng = cfg.engine === "langgraph" ? "LangGraph" : "Dispatcher";
    return `AWS ECS (Fargate) + ${eng}`;
  }
  if (cfg.surface === "http") {
    return cfg.engine === "langgraph" ? "LangGraph + API Server" : "API Server";
  }
  return cfg.engine === "langgraph" ? "LangGraph" : "Simple Runtime";
}

/** Default export config (matches "langgraph" preset) */
export const DEFAULT_EXPORT_CONFIG: ExportConfig = {
  engine: "langgraph",
  surface: "cli",
  packaging: "local",
  isAdvanced: false,
};

export interface ExportFile {
  path: string;
  language: string;
  size: number;
  sha256: string;
  truncated?: boolean;
  isEntrypoint?: boolean;
}

export interface ManifestResponse {
  export_id: string;
  flow_id: string;
  flow_name: string;
  target: ExportTarget;
  total_files: number;
  files: ExportFile[];
  entrypoints: string[];
  truncated: boolean;
  truncation_limit?: number;
  created_at: string;
  etag: string;
}

export interface FileResponse {
  path: string;
  content: string;
  language: string;
  sha256: string;
  truncated: boolean;
  original_size?: number;
}

export interface ExportCreateResponse {
  export_id: string;
  status: "pending" | "ready" | "failed";
  target: ExportTarget;
  manifest_url: string;
  download_url: string;
}

export interface ExportError {
  code: "NOT_FOUND" | "UNSUPPORTED" | "TOO_LARGE" | "SERVER_ERROR";
  message: string;
  detail?: string;
}

// File tree node for UI
export interface FileTreeNode {
  path: string;
  name: string;
  depth: number;
  isFolder: boolean;
  language?: string;
  size?: number;
  sha256?: string;
  truncated?: boolean;
  children?: FileTreeNode[];
  expanded?: boolean;
}

// Cache entry for file contents
export interface CachedFile {
  content: string;
  language: string;
  sha256: string;
  truncated: boolean;
  fetchedAt: number;
}
