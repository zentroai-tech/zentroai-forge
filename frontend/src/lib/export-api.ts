/**
 * API client for export/code preview endpoints
 */

import type {
  ExportCreateResponse,
  ManifestResponse,
  FileResponse,
  ExportError,
  ExportTarget,
  ExportConfig,
} from "@/types/export";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ExportApiError extends Error {
  constructor(
    public code: ExportError["code"],
    message: string,
    public detail?: string
  ) {
    super(message);
    this.name = "ExportApiError";
  }
}

async function handleExportResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code: ExportError["code"] = "SERVER_ERROR";
    let message = `API Error: ${response.status}`;
    let detail: string | undefined;

    if (response.status === 404) {
      code = "NOT_FOUND";
      message = "Export not found";
    } else if (response.status === 415) {
      code = "UNSUPPORTED";
      message = "File type not supported for preview";
    } else if (response.status === 413) {
      code = "TOO_LARGE";
      message = "File too large for preview";
    }

    try {
      const errorBody = await response.json();
      if (errorBody.detail) {
        detail = typeof errorBody.detail === "string"
          ? errorBody.detail
          : JSON.stringify(errorBody.detail);
        if (detail) {
          message = detail;
        }
      }
    } catch {
      // Could not parse error body
    }

    throw new ExportApiError(code, message, detail);
  }

  return response.json();
}

/**
 * Create a new export for a flow (generates code preview).
 *
 * Accepts either:
 * - An ``ExportConfig`` object (advanced composition API)
 * - A legacy ``ExportTarget`` string (preset API, backward compat)
 */
export async function createExport(
  flowId: string,
  configOrTarget: ExportConfig | ExportTarget = "langgraph"
): Promise<ExportCreateResponse> {
  let body: Record<string, string>;

  if (typeof configOrTarget === "string") {
    // Legacy preset
    body = { target: configOrTarget };
  } else {
    // Composable config — send engine/surface/packaging directly
    body = {
      engine: configOrTarget.engine,
      surface: configOrTarget.surface,
      packaging: configOrTarget.packaging,
    };
  }

  const response = await fetch(`${API_BASE_URL}/flows/${flowId}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return handleExportResponse<ExportCreateResponse>(response);
}

/**
 * Get the manifest for an export
 */
export async function getManifest(exportId: string, etag?: string): Promise<ManifestResponse | null> {
  const headers: HeadersInit = {};
  if (etag) {
    headers["If-None-Match"] = etag;
  }

  const response = await fetch(`${API_BASE_URL}/exports/${exportId}/manifest`, {
    headers,
  });

  // 304 Not Modified - manifest hasn't changed
  if (response.status === 304) {
    return null;
  }

  return handleExportResponse<ManifestResponse>(response);
}

/**
 * Get a file's content from an export
 */
export async function getFile(exportId: string, path: string): Promise<FileResponse> {
  const response = await fetch(
    `${API_BASE_URL}/exports/${exportId}/file?path=${encodeURIComponent(path)}`
  );

  return handleExportResponse<FileResponse>(response);
}

/**
 * Get the download URL for an export
 */
export function getDownloadUrl(exportId: string): string {
  return `${API_BASE_URL}/exports/${exportId}/download`;
}

function filenameFromContentDisposition(value: string | null): string | null {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]).trim();
    } catch {
      return utf8Match[1].trim();
    }
  }
  const plainMatch = value.match(/filename="?([^";]+)"?/i);
  if (plainMatch?.[1]) return plainMatch[1].trim();
  return null;
}

/**
 * Download export as ZIP (triggers browser download)
 */
export async function downloadExport(exportId: string, fallbackFilename?: string): Promise<void> {
  const url = `${API_BASE_URL}/exports/${exportId}/download`;

  try {
    const response = await fetch(url);

    if (!response.ok) {
      let errorMessage = `Failed to download export (${response.status})`;
      try {
        const errorBody = await response.json();
        if (errorBody.detail) {
          errorMessage = typeof errorBody.detail === "string"
            ? errorBody.detail
            : JSON.stringify(errorBody.detail);
        }
      } catch {
        // Could not parse error body
      }
      throw new ExportApiError("SERVER_ERROR", errorMessage);
    }

    const blob = await response.blob();
    if (blob.size === 0) {
      throw new ExportApiError("SERVER_ERROR", "Downloaded file is empty");
    }

    const serverFilename = filenameFromContentDisposition(response.headers.get("content-disposition"));
    const finalFilename = serverFilename || fallbackFilename || `export_${exportId}.zip`;

    const objectUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = objectUrl;
    a.download = finalFilename;
    document.body.appendChild(a);
    a.click();

    // Cleanup after a short delay to ensure download starts
    setTimeout(() => {
      window.URL.revokeObjectURL(objectUrl);
      document.body.removeChild(a);
    }, 100);
  } catch (error) {
    if (error instanceof ExportApiError) {
      throw error;
    }
    // Network error or other issue
    throw new ExportApiError("SERVER_ERROR", `Download failed: ${error instanceof Error ? error.message : "Unknown error"}`);
  }
}
