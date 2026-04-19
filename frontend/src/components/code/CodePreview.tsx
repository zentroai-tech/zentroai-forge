"use client";

import { useState, useMemo, useCallback } from "react";
import { useFlowStore } from "@/lib/store";
import { generateCodePreview, type GeneratedFile } from "@/lib/code-generator";
import toast from "react-hot-toast";

interface CodePreviewProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function CodePreview({ isOpen, onClose }: CodePreviewProps) {
  const { currentFlow } = useFlowStore();
  const [selectedFile, setSelectedFile] = useState<string>("main.py");
  const [isExporting, setIsExporting] = useState(false);

  // Generate code preview from current flow
  const generatedFiles = useMemo(() => {
    if (!currentFlow || currentFlow.nodes.length === 0) {
      return [];
    }
    return generateCodePreview(currentFlow);
  }, [currentFlow]);

  // Find selected file content
  const selectedFileContent = useMemo(() => {
    const file = generatedFiles.find((f) => f.name === selectedFile);
    return file?.content || "// Select a file to view";
  }, [generatedFiles, selectedFile]);

  // Export as ZIP
  const handleExport = useCallback(async () => {
    if (!currentFlow?.created_at) {
      toast.error("Please save the flow first before exporting");
      return;
    }

    setIsExporting(true);
    try {
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
      const response = await fetch(`${API_BASE_URL}/flows/${currentFlow.id}/export`, {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Failed to export flow");
      }

      // Download the ZIP file
      const blob = await response.blob();
      const cd = response.headers.get("content-disposition");
      const utf8 = cd?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const plain = cd?.match(/filename=\"?([^\";]+)\"?/i)?.[1];
      const serverFilename = utf8 ? decodeURIComponent(utf8) : plain;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = serverFilename || `${currentFlow.id}_export.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast.success("Flow exported successfully");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to export flow");
    } finally {
      setIsExporting(false);
    }
  }, [currentFlow]);

  // Copy to clipboard
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(selectedFileContent);
    toast.success("Copied to clipboard");
  }, [selectedFileContent]);

  if (!isOpen) return null;

  const canExport = currentFlow?.created_at && currentFlow.nodes.length > 0;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-5xl mx-4 h-[80vh] flex flex-col border"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-[var(--text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              <h2 className="text-lg font-semibold text-white">Code Preview</h2>
            </div>
            <span
              className="text-xs px-2 py-1 rounded"
              style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
            >
              Live Preview
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="btn-pill text-sm flex items-center gap-1"
              title="Copy current file"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting || !canExport}
              className="btn-pill text-sm flex items-center gap-1"
              title={!canExport ? "Save flow first to export" : "Export as ZIP"}
            >
              {isExporting ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Exporting...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Export ZIP
                </>
              )}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
              style={{ color: "var(--text-muted)" }}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* File tree */}
          <div
            className="w-56 border-r overflow-y-auto"
            style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
          >
            <div className="p-2">
              <div className="text-xs font-semibold uppercase px-2 py-1" style={{ color: "var(--text-muted)" }}>
                Files
              </div>
              {generatedFiles.length === 0 ? (
                <p className="text-sm px-2 py-4" style={{ color: "var(--text-muted)" }}>
                  Add nodes to see code preview
                </p>
              ) : (
                <div className="space-y-0.5">
                  {generatedFiles.map((file) => (
                    <button
                      key={file.name}
                      onClick={() => setSelectedFile(file.name)}
                      className="w-full text-left px-2 py-1.5 rounded text-sm flex items-center gap-2 transition-colors"
                      style={{
                        backgroundColor: selectedFile === file.name ? "rgba(139, 148, 158, 0.12)" : "transparent",
                        color: selectedFile === file.name ? "var(--text-primary)" : "var(--text-secondary)",
                      }}
                    >
                      <FileIcon filename={file.name} />
                      <span className="truncate">{file.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Code viewer */}
          <div className="flex-1 overflow-auto" style={{ backgroundColor: "var(--bg-primary)" }}>
            <pre className="p-4 text-sm font-mono leading-relaxed" style={{ color: "var(--text-primary)" }}>
              <code>{selectedFileContent}</code>
            </pre>
          </div>
        </div>

        {/* Footer */}
        <div
          className="p-3 border-t text-xs flex items-center justify-between"
          style={{ borderColor: "var(--border-default)", color: "var(--text-muted)" }}
        >
          <span>
            {generatedFiles.length} files generated
          </span>
          {!canExport && (
            <span style={{ color: "var(--accent-warning)" }}>
              Save flow to enable export
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function FileIcon({ filename }: { filename: string }) {
  const ext = filename.split(".").pop();

  if (ext === "py") {
    return (
      <svg className="w-4 h-4 text-blue-500" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.373 0 6 3.373 6 6v3h6v1H4c-2.21 0-4 2.686-4 6 0 3.314 1.79 6 4 6h2v-3c0-2.21 1.79-4 4-4h6c2.21 0 4-1.79 4-4V6c0-2.627-1.373-6-8-6zm-1 4a1 1 0 110 2 1 1 0 010-2z"/>
        <path d="M18 9v3c0 2.21-1.79 4-4 4h-6c-2.21 0-4 1.79-4 4v3c0 2.627 1.373 6 8 6 6.627 0 8-3.373 8-6v-3h-6v-1h8c2.21 0 4-2.686 4-6 0-3.314-1.79-6-4-6h-2v3c0 2.21-1.79 4-4 4h-4zm1 11a1 1 0 110 2 1 1 0 010-2z"/>
      </svg>
    );
  }

  if (ext === "toml") {
    return (
      <svg className="w-4 h-4 text-orange-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
      </svg>
    );
  }

  if (ext === "md") {
    return (
      <svg className="w-4 h-4 text-slate-500" viewBox="0 0 24 24" fill="currentColor">
        <path d="M22 4H2v16h20V4zM7 15V9h2l2 3 2-3h2v6h-2v-4l-2 3-2-3v4H7zm10 0v-4h-2l3-3 3 3h-2v4h-2z"/>
      </svg>
    );
  }

  return (
    <svg className="w-4 h-4 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
