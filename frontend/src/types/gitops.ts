/**
 * Types for GitOps Export API
 */

export type GitOpsStatus = "pending" | "running" | "success" | "failed";

// GitOps configuration for export
export interface GitOpsConfig {
  repo: string; // owner/name format
  base_branch: string;
  branch_name: string;
  target_path?: string;
  pr_title: string;
  pr_body: string;
  dry_run: boolean;
}

// Request payload for GitOps export
export interface GitOpsExportRequest {
  export_id: string;
  config: GitOpsConfig;
}

// GitOps job status response
export interface GitOpsJobStatus {
  job_id: string;
  export_id: string;
  status: GitOpsStatus;
  pr_url?: string;
  pr_number?: number;
  branch_name?: string;
  logs: string[];
  error_message?: string;
  created_at: string;
  updated_at: string;
}

// Backend configuration status
export interface GitOpsBackendStatus {
  configured: boolean;
  username?: string;
  default_repo?: string;
  permissions?: string[];
}

// Create GitOps export response
export interface GitOpsExportResponse {
  job_id: string;
  status: GitOpsStatus;
  message: string;
}

// GitHub repo from /gitops/repos
export interface GitHubRepo {
  full_name: string; // owner/name
  private: boolean;
  default_branch: string;
  description?: string;
}

// GitHub branch from /gitops/repos/{owner}/{repo}/branches
export interface GitHubBranch {
  name: string;
}
