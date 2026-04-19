"use client";

import { useCallback, useEffect, useState } from "react";
import type { ModelInfo, ModelProvider, ProviderModels } from "@/types/models";
import { fetchModels, refreshModels } from "@/lib/modelCache";

interface UseModelsResult {
  models: ModelInfo[];
  loading: boolean;
  error: string | null;
  warning: string | null;
  lastUpdated: string | null;
  refresh: () => Promise<void>;
}

/**
 * Hook to fetch and cache models for a provider.
 *
 * Uses FE local cache + backend SWR. Exposes a refresh() function
 * for the "Refresh models" button.
 */
export function useModels(
  provider: ModelProvider | "auto",
  projectId: string,
  region?: string | null
): UseModelsResult {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const actualProvider = provider === "auto" ? null : provider;

  const load = useCallback(async () => {
    if (!actualProvider || !projectId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchModels(actualProvider, projectId, region);
      setModels(result.models);
      setWarning(result.warning || null);
      if (result.models.length > 0) {
        setLastUpdated(result.models[0].updated_at);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  }, [actualProvider, projectId, region]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = useCallback(async () => {
    if (!actualProvider || !projectId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await refreshModels(actualProvider, projectId, region);
      setModels(result.models);
      setWarning(result.warning || null);
      if (result.models.length > 0) {
        setLastUpdated(result.models[0].updated_at);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh models");
    } finally {
      setLoading(false);
    }
  }, [actualProvider, projectId, region]);

  return { models, loading, error, warning, lastUpdated, refresh };
}
