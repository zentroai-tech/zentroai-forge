"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import toast from "react-hot-toast";
import {
  downloadIntegrationsLibraryZip,
  getIntegrationsLibraryFile,
  getIntegrationsLibraryIndex,
  type IntegrationLibraryIndex,
} from "@/lib/api";

const CodeMirrorViewer = dynamic(() => import("@/components/code/CodeMirrorViewer"), {
  ssr: false,
});

interface IntegrationsLibraryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type LibraryGroup = "docs" | "shared" | `recipe:${string}`;

function displayGroupName(group: LibraryGroup): string {
  if (group === "docs") return "Docs";
  if (group === "shared") return "Shared Helpers";
  return group.replace("recipe:", "");
}

function fileLabel(path: string): { primary: string; secondary: string } {
  const parts = path.split("/");
  const primary = parts[parts.length - 1] || path;
  const secondary = parts.slice(0, -1).join("/");
  return { primary, secondary };
}

function detectLanguage(path: string): string {
  const lower = path.toLowerCase();
  if (lower.endsWith(".md")) return "markdown";
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
  if (lower.endsWith(".toml")) return "toml";
  return "text";
}

export default function IntegrationsLibraryModal({ isOpen, onClose }: IntegrationsLibraryModalProps) {
  const [index, setIndex] = useState<IntegrationLibraryIndex | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<LibraryGroup>("docs");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);
    getIntegrationsLibraryIndex()
      .then((data) => {
        setIndex(data);
      })
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : "Failed to load integrations library");
      })
      .finally(() => setIsLoading(false));
  }, [isOpen]);

  const filesForGroup = useMemo(() => {
    if (!index) return [] as string[];
    if (selectedGroup === "docs") return index.docs_files;
    if (selectedGroup === "shared") return index.shared_files;
    const recipeId = selectedGroup.replace("recipe:", "");
    return index.recipes[recipeId] || [];
  }, [index, selectedGroup]);

  const selectedRecipe = useMemo(
    () => (selectedGroup.startsWith("recipe:") ? selectedGroup.replace("recipe:", "") : null),
    [selectedGroup]
  );

  useEffect(() => {
    if (!isOpen || !index) return;
    if (filesForGroup.length === 0) {
      setSelectedPath(null);
      setFileContent("");
      return;
    }
    if (!selectedPath || !filesForGroup.includes(selectedPath)) {
      setSelectedPath(filesForGroup[0]);
    }
  }, [isOpen, index, filesForGroup, selectedPath]);

  useEffect(() => {
    if (!isOpen || !selectedPath) return;
    setIsLoadingFile(true);
    getIntegrationsLibraryFile(selectedPath)
      .then((data) => setFileContent(data.content))
      .catch((error) => {
        setFileContent("");
        toast.error(error instanceof Error ? error.message : "Failed to load file");
      })
      .finally(() => setIsLoadingFile(false));
  }, [isOpen, selectedPath]);

  if (!isOpen) return null;

  const groups: LibraryGroup[] = [
    "docs",
    "shared",
    ...Object.keys(index?.recipes || {}).map((recipe) => `recipe:${recipe}` as LibraryGroup),
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className="w-[min(1600px,95vw)] h-[85vh] max-h-[920px] rounded-xl border overflow-hidden flex flex-col"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="h-12 px-4 flex items-center justify-between border-b" style={{ borderColor: "var(--border-default)" }}>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">Integrations Library</h2>
          <div className="flex items-center gap-2">
            <button
              className="btn-secondary px-2.5 py-1 text-xs"
              disabled={isExporting}
              onClick={async () => {
                try {
                  setIsExporting(true);
                  await downloadIntegrationsLibraryZip(selectedRecipe || undefined);
                  toast.success(selectedRecipe ? "Recipe ZIP exported" : "Library ZIP exported");
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "Failed to export zip");
                } finally {
                  setIsExporting(false);
                }
              }}
              title={selectedRecipe ? `Export ${selectedRecipe} as plug-and-play ZIP` : "Export full integrations library ZIP"}
            >
              {isExporting ? "Exporting..." : "Export ZIP"}
            </button>
            <button onClick={onClose} className="btn-secondary px-2.5 py-1 text-xs">
              Close
            </button>
          </div>
        </div>
        <div className="grid grid-cols-12 flex-1 min-h-0 overflow-hidden">
          <div className="col-span-3 border-r p-3 min-h-0 overflow-hidden flex flex-col" style={{ borderColor: "var(--border-default)" }}>
            <div className="mb-2 text-xs font-semibold text-[var(--text-secondary)]">Collections</div>
            <div className="space-y-1 overflow-auto pr-1 min-h-0">
              {groups.map((group) => (
                <button
                  key={group}
                  className="w-full text-left rounded-md px-3 py-2 text-sm"
                  style={{
                    backgroundColor: selectedGroup === group ? "var(--bg-selected)" : "transparent",
                    border: `1px solid ${selectedGroup === group ? "var(--border-active)" : "var(--border-default)"}`,
                    color: selectedGroup === group ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                  onClick={() => setSelectedGroup(group)}
                >
                  {displayGroupName(group)}
                </button>
              ))}
            </div>
          </div>
          <div className="col-span-3 border-r p-3 min-h-0 overflow-hidden flex flex-col" style={{ borderColor: "var(--border-default)" }}>
            <div className="mb-2 text-xs font-semibold text-[var(--text-secondary)]">
              Files · {displayGroupName(selectedGroup)}
            </div>
            {isLoading ? (
              <p className="text-sm text-[var(--text-muted)]">Loading...</p>
            ) : filesForGroup.length === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">No files in this section.</p>
            ) : (
              <div className="space-y-1 overflow-auto pr-1 min-h-0">
                {filesForGroup.map((path) => {
                  const label = fileLabel(path);
                  return (
                    <button
                      key={path}
                      title={path}
                      className="w-full text-left rounded-md px-2.5 py-2"
                      style={{
                        backgroundColor: selectedPath === path ? "var(--bg-selected)" : "transparent",
                        border: `1px solid ${selectedPath === path ? "var(--border-active)" : "var(--border-default)"}`,
                        color: selectedPath === path ? "var(--text-primary)" : "var(--text-secondary)",
                      }}
                      onClick={() => setSelectedPath(path)}
                    >
                      <div className="text-xs font-mono truncate">{label.primary}</div>
                      {label.secondary && (
                        <div className="text-[10px] truncate text-[var(--text-muted)]">{label.secondary}</div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <div className="col-span-6 min-h-0 overflow-hidden flex flex-col">
            <CodeMirrorViewer
              content={fileContent}
              language={selectedPath ? detectLanguage(selectedPath) : "text"}
              path={selectedPath || "Select a file"}
              isLoading={isLoadingFile}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
