"use client";

import { useState, useRef } from "react";
import toast from "react-hot-toast";
import { uploadDataset } from "@/lib/evalsApi";

interface DatasetUploadModalProps {
  suiteId: string;
  onClose: () => void;
  onImported: (count: number) => void;
}

export default function DatasetUploadModal({ suiteId, onClose, onImported }: DatasetUploadModalProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      toast.error("Please select a JSONL file");
      return;
    }
    setIsUploading(true);
    try {
      const result = await uploadDataset(suiteId, selectedFile);
      onImported(result.imported_cases);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div
        className="rounded-xl shadow-2xl w-full max-w-md mx-4 border"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border-default)",
        }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--border-default)" }}
        >
          <h2 className="text-base font-semibold text-white">Upload Dataset (JSONL)</h2>
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

        {/* Body */}
        <div className="p-6 space-y-4">
          <p className="text-sm text-[var(--text-muted)]">
            Upload a JSONL file — one JSON object per line. Each object must have at least an{" "}
            <code className="px-1 py-0.5 rounded text-xs bg-[var(--bg-tertiary)] font-mono">input</code> field.
          </p>
          <div className="rounded-lg border border-dashed p-3 text-xs font-mono text-[var(--text-muted)] overflow-auto"
            style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-primary)" }}>
            {`{"id":"case-001","input":"What is 2+2?","expected":{"answer":"4"}}\n{"id":"case-002","input":"Cite your sources.","assertions":[{"type":"citation_required","field":"output"}]}`}
          </div>

          {/* File picker */}
          <div>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="btn-secondary w-full text-sm flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              {selectedFile ? selectedFile.name : "Choose .jsonl file"}
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".jsonl,.ndjson,text/plain"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary flex-1 text-sm"
              disabled={isUploading}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={isUploading || !selectedFile}
              className="btn-pill flex-1 text-sm flex items-center justify-center gap-2"
            >
              {isUploading && (
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {isUploading ? "Uploading…" : "Import Cases"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
