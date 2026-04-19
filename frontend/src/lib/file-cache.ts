/**
 * Client-side cache for file contents
 */

import type { CachedFile } from "@/types/export";

// Cache TTL: 30 minutes
const CACHE_TTL = 30 * 60 * 1000;

// Maximum cache size (number of files)
const MAX_CACHE_SIZE = 100;

class FileCache {
  private cache = new Map<string, CachedFile>();

  private getCacheKey(exportId: string, path: string): string {
    return `${exportId}:${path}`;
  }

  /**
   * Get a cached file if it exists and matches the expected sha256
   */
  get(exportId: string, path: string, expectedSha256: string): CachedFile | null {
    const key = this.getCacheKey(exportId, path);
    const cached = this.cache.get(key);

    if (!cached) {
      return null;
    }

    // Check if cache entry is expired
    if (Date.now() - cached.fetchedAt > CACHE_TTL) {
      this.cache.delete(key);
      return null;
    }

    // Check if sha256 matches (file might have changed)
    if (cached.sha256 !== expectedSha256) {
      this.cache.delete(key);
      return null;
    }

    return cached;
  }

  /**
   * Store a file in the cache
   */
  set(
    exportId: string,
    path: string,
    content: string,
    language: string,
    sha256: string,
    truncated: boolean
  ): void {
    // Evict oldest entries if cache is full
    if (this.cache.size >= MAX_CACHE_SIZE) {
      this.evictOldest();
    }

    const key = this.getCacheKey(exportId, path);
    this.cache.set(key, {
      content,
      language,
      sha256,
      truncated,
      fetchedAt: Date.now(),
    });
  }

  /**
   * Remove oldest cache entries
   */
  private evictOldest(): void {
    const entries = Array.from(this.cache.entries());
    entries.sort((a, b) => a[1].fetchedAt - b[1].fetchedAt);

    // Remove oldest 20% of entries
    const toRemove = Math.ceil(entries.length * 0.2);
    for (let i = 0; i < toRemove; i++) {
      this.cache.delete(entries[i][0]);
    }
  }

  /**
   * Clear all cached files for an export
   */
  clearExport(exportId: string): void {
    const keysToDelete: string[] = [];
    this.cache.forEach((_, key) => {
      if (key.startsWith(`${exportId}:`)) {
        keysToDelete.push(key);
      }
    });
    keysToDelete.forEach((key) => this.cache.delete(key));
  }

  /**
   * Clear entire cache
   */
  clear(): void {
    this.cache.clear();
  }

  /**
   * Get cache statistics
   */
  getStats(): { size: number; maxSize: number } {
    return {
      size: this.cache.size,
      maxSize: MAX_CACHE_SIZE,
    };
  }
}

// Singleton instance
export const fileCache = new FileCache();
