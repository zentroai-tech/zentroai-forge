/**
 * Types for Model Registry
 */

export type ModelProvider = "openai" | "anthropic" | "gemini";

export interface ModelInfo {
  id: string;
  label: string;
  status: "available" | "unavailable";
  updated_at: string; // ISO 8601
}

export interface ProviderModels {
  provider: ModelProvider;
  models: ModelInfo[];
  warning?: string | null;
}

export interface ProviderInfo {
  id: ModelProvider;
  label: string;
}

export interface ProvidersResponse {
  providers: ProviderInfo[];
}

/** Shape stored in localStorage */
export interface ModelCacheEntry {
  payload: ProviderModels;
  etag: string;
  fetched_at: number; // epoch ms
}

/** Recommended models to show at the top of dropdowns */
export const RECOMMENDED_MODELS: Record<ModelProvider, string[]> = {
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  anthropic: ["claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001", "claude-opus-4-6"],
  gemini: ["gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash"],
};
