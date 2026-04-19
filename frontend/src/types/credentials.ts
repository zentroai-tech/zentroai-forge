/**
 * Types for Provider Credentials Management
 *
 * Matches backend API at /api/credentials
 */

export type CredentialProvider = "openai" | "anthropic" | "gemini";

export type CredentialScopeType = "workspace" | "project";

export type TestStatus = "untested" | "ok" | "fail";

export interface Credential {
  id: string;
  provider: CredentialProvider;
  scope_type: CredentialScopeType;
  scope_id: string;
  name: string | null;
  created_at: string;
  updated_at: string;
  last_test_status: TestStatus | null;
  last_tested_at: string | null;
  last_test_error: string | null;
}

export interface CredentialListResponse {
  credentials: Credential[];
  total: number;
}

export interface CreateCredentialRequest {
  provider: CredentialProvider;
  scope_type: CredentialScopeType;
  scope_id: string;
  name?: string;
  secret: string;
}

export interface UpdateCredentialRequest {
  secret?: string;
  name?: string;
}

export interface TestCredentialResponse {
  id: string;
  provider: string;
  status: TestStatus;
  tested_at: string;
  error?: string | null;
}

export interface CredentialError {
  type: "missing_credential";
  provider: CredentialProvider;
  scope: CredentialScopeType;
  message: string;
}

export const PROVIDER_INFO: Record<CredentialProvider, { label: string; icon: string; placeholder: string }> = {
  openai: {
    label: "OpenAI",
    icon: "🤖",
    placeholder: "sk-...",
  },
  anthropic: {
    label: "Anthropic (Claude)",
    icon: "🧠",
    placeholder: "sk-ant-...",
  },
  gemini: {
    label: "Google Gemini",
    icon: "✨",
    placeholder: "AIza...",
  },
};
