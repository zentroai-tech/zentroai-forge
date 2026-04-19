"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import toast from "react-hot-toast";
import { useFlowStore } from "@/lib/store";
import {
  createExport,
  getManifest,
  getFile,
  downloadExport,
  ExportApiError,
} from "@/lib/export-api";
import { fileCache } from "@/lib/file-cache";
import FileTree from "./FileTree";
import GitOpsExportModal from "./GitOpsExportModal";
import type { ManifestResponse, ExportConfig, ExportEngine, ExportSurface, ExportPackaging } from "@/types/export";
import { EXPORT_PRESETS, exportConfigLabel, DEFAULT_EXPORT_CONFIG } from "@/types/export";

// Dynamically import CodeMirror to avoid SSR issues
const CodeMirrorViewer = dynamic(() => import("./CodeMirrorViewer"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full text-[var(--text-muted)]" style={{ backgroundColor: "var(--bg-primary)" }}>
      Loading editor...
    </div>
  ),
});

interface CodePreviewTabProps {
  isOpen: boolean;
  onClose: () => void;
  embedded?: boolean;
}

export default function CodePreviewTab({ isOpen, onClose, embedded }: CodePreviewTabProps) {
  const { currentFlow } = useFlowStore();

  // Export config state
  const [exportConfig, setExportConfig] = useState<ExportConfig>(DEFAULT_EXPORT_CONFIG);
  const [showAdvanced, setShowAdvanced] = useState(false);
  // Draft state for the advanced popover (not committed until Apply)
  const [draft, setDraft] = useState<Omit<ExportConfig, "isAdvanced">>(DEFAULT_EXPORT_CONFIG);
  const advancedRef = useRef<HTMLDivElement>(null);

  // Export state
  const [exportId, setExportId] = useState<string | null>(null);
  const [manifest, setManifest] = useState<ManifestResponse | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  // File viewing state
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [fileLanguage, setFileLanguage] = useState<string>("text");
  const [fileTruncated, setFileTruncated] = useState(false);
  const [fileOriginalSize, setFileOriginalSize] = useState<number | undefined>();
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  // GitOps modal state
  const [showGitOpsModal, setShowGitOpsModal] = useState(false);

  // Generate export (create code preview)
  const handleGeneratePreview = useCallback(async () => {
    if (!currentFlow?.created_at) {
      toast.error("Please save the flow first");
      return;
    }

    setIsGenerating(true);
    setExportId(null);
    setManifest(null);
    setSelectedPath(null);
    setFileContent("");
    setFileError(null);

    try {
      const response = await createExport(currentFlow.id, exportConfig);
      setExportId(response.export_id);

      // Fetch manifest
      const manifestData = await getManifest(response.export_id);
      if (manifestData) {
        setManifest(manifestData);

        // Auto-select first entrypoint or first file
        if (manifestData.files.length > 0) {
          // Prefer entrypoints from manifest
          const entryFile = manifestData.entrypoints?.length > 0
            ? manifestData.files.find((f) => manifestData.entrypoints.includes(f.path))
            : manifestData.files.find(
                (f) => f.path.endsWith("main.py") || f.path.endsWith("graph.py")
              );
          setSelectedPath(entryFile?.path || manifestData.files[0].path);
        }
      }

      toast.success("Code preview generated");
    } catch (error) {
      if (error instanceof ExportApiError) {
        toast.error(error.message);
      } else {
        toast.error("Failed to generate preview");
      }
    } finally {
      setIsGenerating(false);
    }
  }, [currentFlow, exportConfig]);

  // Load file content
  const loadFile = useCallback(async (path: string) => {
    if (!exportId || !manifest) return;

    const file = manifest.files.find((f) => f.path === path);
    if (!file) {
      setFileError("File not found in manifest");
      return;
    }

    setSelectedPath(path);
    setFileError(null);

    // Check cache first
    const cached = fileCache.get(exportId, path, file.sha256);
    if (cached) {
      setFileContent(cached.content);
      setFileLanguage(cached.language);
      setFileTruncated(cached.truncated);
      setFileOriginalSize(undefined);
      return;
    }

    // Fetch from API
    setIsLoadingFile(true);
    try {
      const response = await getFile(exportId, path);
      setFileContent(response.content);
      setFileLanguage(response.language);
      setFileTruncated(response.truncated);
      setFileOriginalSize(response.original_size);

      // Cache the response
      fileCache.set(
        exportId,
        path,
        response.content,
        response.language,
        response.sha256,
        response.truncated
      );
    } catch (error) {
      if (error instanceof ExportApiError) {
        if (error.code === "UNSUPPORTED") {
          setFileError("Binary/unsupported file (not previewable)");
        } else if (error.code === "TOO_LARGE") {
          setFileError("File too large for preview. Download ZIP to view.");
        } else {
          setFileError(error.message);
        }
      } else {
        setFileError("Failed to load file");
      }
      setFileContent("");
    } finally {
      setIsLoadingFile(false);
    }
  }, [exportId, manifest]);

  // Load file when selection changes
  useEffect(() => {
    if (selectedPath && exportId && manifest) {
      loadFile(selectedPath);
    }
  }, [selectedPath, exportId, manifest, loadFile]);

  // Download ZIP
  const handleDownload = useCallback(async () => {
    if (!exportId || !manifest) return;

    setIsDownloading(true);
    try {
      const today = new Date();
      const dd = String(today.getDate()).padStart(2, "0");
      const mm = String(today.getMonth() + 1).padStart(2, "0");
      const yyyy = String(today.getFullYear());
      const safeFlowName = (manifest.flow_name || "forge_export")
        .replace(/[^a-zA-Z0-9-_]/g, "_")
        .replace(/^_+|_+$/g, "") || "forge_export";
      const target = (manifest.target || "langgraph")
        .replace(/[^a-zA-Z0-9-_]/g, "_")
        .replace(/^_+|_+$/g, "") || "langgraph";
      const fallbackName = `${safeFlowName}_export_${target}_${dd}_${mm}_${yyyy}.zip`;
      await downloadExport(exportId, fallbackName);
      toast.success("Download started");
    } catch (error) {
      const message = error instanceof ExportApiError
        ? error.message
        : "Failed to download";
      toast.error(message);
      console.error("Download error:", error);
    } finally {
      setIsDownloading(false);
    }
  }, [exportId, manifest]);

  // Close Advanced popover on outside click
  useEffect(() => {
    if (!showAdvanced) return;
    function handleClick(e: MouseEvent) {
      if (advancedRef.current && !advancedRef.current.contains(e.target as Node)) {
        setShowAdvanced(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showAdvanced]);

  if (!embedded && !isOpen) return null;

  const canGenerate = currentFlow?.created_at && currentFlow.nodes && currentFlow.nodes.length > 0;

  const embeddedToolbar = (
    <div
      className="flex items-center justify-between px-4 py-2 border-b flex-shrink-0"
      style={{ borderColor: "var(--border-default)" }}
    >
      <div className="flex items-center gap-2">
        {manifest && (
          <span
            className="text-xs px-2 py-1 rounded"
            style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
          >
            {manifest.total_files} files
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {/* Target selector + Advanced popover */}
        <div className="relative flex items-center gap-2" ref={advancedRef}>
          <label className="text-xs" style={{ color: "var(--text-muted)" }}>Target:</label>
          <select
            value={exportConfig.isAdvanced ? "__advanced__" : (
              EXPORT_PRESETS.find(
                (p) => p.config.engine === exportConfig.engine &&
                       p.config.surface === exportConfig.surface &&
                       p.config.packaging === exportConfig.packaging
              )?.id ?? "__advanced__"
            )}
            onChange={(e) => {
              const val = e.target.value;
              if (val === "__advanced__") {
                setDraft({ engine: exportConfig.engine, surface: exportConfig.surface, packaging: exportConfig.packaging });
                setShowAdvanced(true);
              } else {
                const preset = EXPORT_PRESETS.find((p) => p.id === val);
                if (preset) {
                  setExportConfig({ ...preset.config, isAdvanced: false });
                  setShowAdvanced(false);
                }
              }
            }}
            disabled={isGenerating}
            className="text-sm rounded px-2 py-1 focus:outline-none focus:border-[var(--border-active)]"
            style={{ backgroundColor: "var(--bg-tertiary)", borderColor: "var(--border-default)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }}
          >
            {EXPORT_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}{p.recommended ? " (Recommended)" : ""}
              </option>
            ))}
            <option disabled style={{ borderTop: "1px solid var(--border-default)" }}>──────────</option>
            <option value="__advanced__">
              {exportConfig.isAdvanced ? `✦ ${exportConfigLabel(exportConfig)}` : "Advanced…"}
            </option>
          </select>

          {/* Advanced popover */}
          {showAdvanced && (
            <div
              className="absolute top-full right-0 mt-2 z-50 rounded-xl border shadow-2xl p-4 w-72"
              style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-white">Advanced Export</span>
                <button
                  onClick={() => setShowAdvanced(false)}
                  className="p-1 rounded hover:bg-[var(--bg-tertiary)]"
                  style={{ color: "var(--text-muted)" }}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-3">
                {/* Engine */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
                    Engine
                  </label>
                  <select
                    value={draft.engine}
                    onChange={(e) => setDraft((d) => ({ ...d, engine: e.target.value as ExportEngine }))}
                    className="w-full text-sm rounded px-2 py-1.5 focus:outline-none"
                    style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
                  >
                    <option value="dispatcher">Dispatcher (default)</option>
                    <option value="langgraph">LangGraph</option>
                  </select>
                </div>

                {/* Surface */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
                    Exposure
                  </label>
                  <select
                    value={draft.surface}
                    onChange={(e) => {
                      const s = e.target.value as ExportSurface;
                      setDraft((d) => ({
                        ...d,
                        surface: s,
                        // Force local packaging if switching away from http
                        packaging: s === "cli" && d.packaging === "aws-ecs" ? "local" : d.packaging,
                      }));
                    }}
                    className="w-full text-sm rounded px-2 py-1.5 focus:outline-none"
                    style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
                  >
                    <option value="cli">CLI (python main.py)</option>
                    <option value="http">HTTP (FastAPI / uvicorn)</option>
                  </select>
                </div>

                {/* Packaging */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
                    Packaging
                  </label>
                  <select
                    value={draft.packaging}
                    onChange={(e) => setDraft((d) => ({ ...d, packaging: e.target.value as ExportPackaging }))}
                    disabled={draft.surface === "cli"}
                    className="w-full text-sm rounded px-2 py-1.5 focus:outline-none disabled:opacity-40"
                    style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
                  >
                    <option value="local">Local (Docker)</option>
                    <option value="aws-ecs">AWS ECS (Fargate + Terraform)</option>
                  </select>
                  {draft.surface === "cli" && (
                    <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                      AWS ECS requires HTTP surface.
                    </p>
                  )}
                </div>

                {/* Preview label */}
                <div
                  className="rounded-lg px-3 py-2 text-xs"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
                >
                  Result: <span className="font-medium text-white">
                    {exportConfigLabel({ ...draft, isAdvanced: true })}
                  </span>
                </div>

                {/* Buttons */}
                <div className="flex gap-2 pt-1">
                  <button
                    onClick={() => {
                      const preset = EXPORT_PRESETS[0]; // Reset to LangGraph
                      setExportConfig({ ...preset.config, isAdvanced: false });
                      setDraft(preset.config);
                      setShowAdvanced(false);
                    }}
                    className="btn-secondary flex-1 text-xs"
                  >
                    Reset
                  </button>
                  <button
                    onClick={() => {
                      setExportConfig({ ...draft, isAdvanced: true });
                      setShowAdvanced(false);
                    }}
                    className="btn-pill flex-1 text-xs"
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
        {!manifest ? (
          <button onClick={handleGeneratePreview} disabled={isGenerating || !canGenerate} className="btn-pill text-sm flex items-center gap-2">
            {isGenerating ? "Generating..." : "Generate Preview"}
          </button>
        ) : (
          <>
            <button onClick={handleGeneratePreview} disabled={isGenerating} className="btn-secondary text-sm" title="Regenerate">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <button onClick={handleDownload} disabled={isDownloading} className="btn-pill text-sm flex items-center gap-2">
              {isDownloading ? "Downloading..." : "Download ZIP"}
            </button>
            <button onClick={() => setShowGitOpsModal(true)} className="btn-secondary text-sm flex items-center gap-2" title="Open PR">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              Open PR
            </button>
          </>
        )}
      </div>
    </div>
  );

  const truncationWarning = manifest?.truncated ? (
    <div
      className="px-4 py-2 border-b text-sm flex items-center gap-2"
      style={{
        backgroundColor: "rgba(234, 179, 8, 0.1)",
        borderColor: "rgba(234, 179, 8, 0.2)",
        color: "var(--accent-warning)"
      }}
    >
      <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <span>
        File list truncated (showing {manifest.files.length} of {manifest.total_files} files).
        Download ZIP to access all files.
      </span>
    </div>
  ) : null;

  const mainContent = (
    <div className="flex-1 flex overflow-hidden">
      {!manifest ? (
        <div className="flex-1 flex items-center justify-center" style={{ backgroundColor: "var(--bg-primary)" }}>
          <div className="text-center p-8">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl flex items-center justify-center border" style={{ backgroundColor: "var(--bg-tertiary)", borderColor: "var(--border-default)" }}>
              <svg className="w-10 h-10 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-white mb-2">Preview Generated Code</h3>
            <p className="mb-6 max-w-md" style={{ color: "var(--text-secondary)" }}>
              Generate a preview of the Python code that will be exported for your agent flow.
            </p>
            {!canGenerate && (
              <p className="text-sm mb-4" style={{ color: "var(--accent-warning)" }}>
                {!currentFlow?.created_at ? "Save your flow first to generate a preview" : "Add at least one node to generate a preview"}
              </p>
            )}
            <button onClick={handleGeneratePreview} disabled={isGenerating || !canGenerate} className="btn-pill">
              {isGenerating ? "Generating..." : "Generate Preview"}
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="w-64 border-r overflow-hidden" style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}>
            <FileTree files={manifest.files} selectedPath={selectedPath} onSelectFile={setSelectedPath} isLoading={isGenerating} entrypoints={manifest.entrypoints} />
          </div>
          <div className="flex-1 overflow-hidden" style={{ backgroundColor: "var(--bg-primary)" }}>
            {selectedPath ? (
              <CodeMirrorViewer content={fileContent} language={fileLanguage} path={selectedPath} truncated={fileTruncated} originalSize={fileOriginalSize} isLoading={isLoadingFile} error={fileError || undefined} />
            ) : (
              <div className="flex items-center justify-center h-full" style={{ color: "var(--text-muted)" }}>Select a file to view</div>
            )}
          </div>
        </>
      )}
    </div>
  );

  const footer = manifest ? (
    <div className="px-4 py-2 border-t text-xs flex items-center justify-between" style={{ borderColor: "var(--border-default)", color: "var(--text-muted)" }}>
      <span>Flow: {manifest.flow_name} | Generated: {new Date(manifest.created_at).toLocaleString()}</span>
      <div className="flex items-center gap-3">
        <span className="px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}>
          {EXPORT_PRESETS.find(p => p.id === manifest.target)?.label || manifest.target}
        </span>
        <span>Export ID: {manifest.export_id.slice(0, 8)}...</span>
      </div>
    </div>
  ) : null;

  const gitOpsModal = showGitOpsModal && exportId && manifest ? (
    <GitOpsExportModal exportId={exportId} flowName={manifest.flow_name} onClose={() => setShowGitOpsModal(false)} />
  ) : null;

  if (embedded) return (
    <div className="h-full flex flex-col">
      {embeddedToolbar}
      {truncationWarning}
      {mainContent}
      {footer}
      {gitOpsModal}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-6xl mx-4 h-[85vh] flex flex-col border"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border-default)" }}>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              <h2 className="text-lg font-semibold text-white">Code Preview</h2>
            </div>
            {manifest && (
              <span className="text-xs px-2 py-1 rounded" style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}>
                {manifest.total_files} files
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <label className="text-xs" style={{ color: "var(--text-muted)" }}>Target:</label>
              <select
                value={exportConfig.isAdvanced ? "__advanced__" : (
                  EXPORT_PRESETS.find(
                    (p) => p.config.engine === exportConfig.engine &&
                           p.config.surface === exportConfig.surface &&
                           p.config.packaging === exportConfig.packaging
                  )?.id ?? "__advanced__"
                )}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val !== "__advanced__") {
                    const preset = EXPORT_PRESETS.find((p) => p.id === val);
                    if (preset) setExportConfig({ ...preset.config, isAdvanced: false });
                  }
                }}
                disabled={isGenerating}
                className="text-sm rounded px-2 py-1 focus:outline-none focus:border-[var(--border-active)]"
                style={{ backgroundColor: "var(--bg-tertiary)", borderColor: "var(--border-default)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }}
              >
                {EXPORT_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}{p.recommended ? " (Recommended)" : ""}</option>
                ))}
              </select>
            </div>
            {!manifest ? (
              <button onClick={handleGeneratePreview} disabled={isGenerating || !canGenerate} className="btn-pill text-sm flex items-center gap-2" title={!canGenerate ? "Save flow first" : "Generate code preview"}>
                {isGenerating ? "Generating..." : "Generate Preview"}
              </button>
            ) : (
              <>
                <button onClick={handleGeneratePreview} disabled={isGenerating} className="btn-secondary text-sm" title="Regenerate preview">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                </button>
                <button onClick={handleDownload} disabled={isDownloading} className="btn-pill text-sm flex items-center gap-2">
                  {isDownloading ? "Downloading..." : "Download ZIP"}
                </button>
                <button onClick={() => setShowGitOpsModal(true)} className="btn-secondary text-sm flex items-center gap-2" title="Open PR to GitHub">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" /></svg>
                  Open PR
                </button>
              </>
            )}
            <button onClick={onClose} className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]" style={{ color: "var(--text-muted)" }}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        {truncationWarning}
        {mainContent}
        {footer}
      </div>
      {gitOpsModal}
    </div>
  );
}
