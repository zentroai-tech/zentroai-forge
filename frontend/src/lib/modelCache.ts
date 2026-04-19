/**
 * Model Registry - FE local cache with SWR pattern.
 *
 * Stores per (project_id, provider, region) in localStorage:
 *   { payload, etag, fetched_at }
 *
 * On page load:
 *   - If local cache exists and not expired -> use it (no network call).
 *   - Else call backend GET models with If-None-Match: <etag>
 *     - 304 -> keep local payload, update fetched_at.
 *     - 200 -> store new payload + etag + fetched_at.
 */

import type {
  ModelProvider,
  ProviderModels,
  ModelCacheEntry,
} from "@/types/models";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** FE cache TTL in ms (24 hours, configurable) */
const FE_TTL_MS = 24 * 60 * 60 * 1000;

const STORAGE_PREFIX = "model_cache:";

function cacheKey(
  projectId: string,
  provider: ModelProvider,
  region?: string | null
): string {
  return `${STORAGE_PREFIX}${projectId}:${provider}:${region || ""}`;
}

function getLocalCache(key: string): ModelCacheEntry | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as ModelCacheEntry;
  } catch {
    return null;
  }
}

function setLocalCache(key: string, entry: ModelCacheEntry): void {
  try {
    localStorage.setItem(key, JSON.stringify(entry));
  } catch {
    // localStorage full or unavailable - ignore
  }
}

/**
 * Fetch models for a provider, using local cache + backend SWR.
 */
export async function fetchModels(
  provider: ModelProvider,
  projectId: string,
  region?: string | null
): Promise<ProviderModels> {
  const key = cacheKey(projectId, provider, region);
  const cached = getLocalCache(key);

  // Check if local cache is still fresh
  if (cached && Date.now() - cached.fetched_at < FE_TTL_MS) {
    return cached.payload;
  }

  // Build URL
  const params = new URLSearchParams({ project_id: projectId });
  if (region) params.append("region", region);
  const url = `${API_BASE_URL}/api/providers/${provider}/models?${params}`;

  // Prepare headers
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (cached?.etag) {
    headers["If-None-Match"] = `"${cached.etag}"`;
  }

  const response = await fetch(url, { headers });

  if (response.status === 304 && cached) {
    // Not modified - update fetched_at
    const updated: ModelCacheEntry = { ...cached, fetched_at: Date.now() };
    setLocalCache(key, updated);
    return cached.payload;
  }

  if (!response.ok) {
    // If we have stale cache, return it
    if (cached) return cached.payload;
    throw new Error(
      `Failed to fetch models for ${provider}: ${response.status}`
    );
  }

  const data = (await response.json()) as ProviderModels;
  const etag = (response.headers.get("etag") || "").replace(/"/g, "");

  const entry: ModelCacheEntry = {
    payload: data,
    etag,
    fetched_at: Date.now(),
  };
  setLocalCache(key, entry);

  return data;
}

/**
 * Force-refresh models from provider (calls POST refresh).
 */
export async function refreshModels(
  provider: ModelProvider,
  projectId: string,
  region?: string | null
): Promise<ProviderModels> {
  const params = new URLSearchParams({ project_id: projectId });
  if (region) params.append("region", region);
  const url = `${API_BASE_URL}/api/providers/${provider}/models/refresh?${params}`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    throw new Error(
      `Failed to refresh models for ${provider}: ${response.status}`
    );
  }

  const data = (await response.json()) as ProviderModels;
  const etag = (response.headers.get("etag") || "").replace(/"/g, "");

  const key = cacheKey(projectId, provider, region);
  const entry: ModelCacheEntry = {
    payload: data,
    etag,
    fetched_at: Date.now(),
  };
  setLocalCache(key, entry);

  return data;
}

/**
 * Clear local cache for a specific provider or all providers.
 */
export function clearModelCache(
  projectId?: string,
  provider?: ModelProvider
): void {
  try {
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!k || !k.startsWith(STORAGE_PREFIX)) continue;
      if (projectId && !k.includes(projectId)) continue;
      if (provider && !k.includes(provider)) continue;
      keysToRemove.push(k);
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
  } catch {
    // ignore
  }
}
