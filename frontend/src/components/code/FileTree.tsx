"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import type { ExportFile, FileTreeNode } from "@/types/export";

interface FileTreeProps {
  files: ExportFile[];
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  isLoading?: boolean;
  entrypoints?: string[];
}

// File icon based on language/extension
function FileIcon({ language, path }: { language: string; path: string }) {
  const ext = path.split(".").pop()?.toLowerCase();

  // Python
  if (language === "python" || ext === "py") {
    return (
      <svg className="w-4 h-4 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.373 0 6 3.373 6 6v3h6v1H4c-2.21 0-4 2.686-4 6 0 3.314 1.79 6 4 6h2v-3c0-2.21 1.79-4 4-4h6c2.21 0 4-1.79 4-4V6c0-2.627-1.373-6-8-6zm-1 4a1 1 0 110 2 1 1 0 010-2z"/>
        <path d="M18 9v3c0 2.21-1.79 4-4 4h-6c-2.21 0-4 1.79-4 4v3c0 2.627 1.373 6 8 6 6.627 0 8-3.373 8-6v-3h-6v-1h8c2.21 0 4-2.686 4-6 0-3.314-1.79-6-4-6h-2v3c0 2.21-1.79 4-4 4h-4zm1 11a1 1 0 110 2 1 1 0 010-2z"/>
      </svg>
    );
  }

  // JavaScript/TypeScript
  if (["javascript", "typescript", "js", "ts", "jsx", "tsx"].includes(language) ||
      ["js", "ts", "jsx", "tsx"].includes(ext || "")) {
    const isTS = language.includes("typescript") || ext === "ts" || ext === "tsx";
    return (
      <svg className={`w-4 h-4 ${isTS ? "text-blue-500" : "text-yellow-400"}`} viewBox="0 0 24 24" fill="currentColor">
        <path d="M3 3h18v18H3V3zm16.525 13.707c-.131-.821-.666-1.511-2.252-2.155-.552-.259-1.165-.438-1.349-.854-.068-.248-.078-.382-.034-.529.113-.484.687-.629 1.137-.495.293.086.567.299.771.584.794-.523.794-.523 1.349-.869-.201-.319-.301-.461-.439-.618-.458-.54-1.074-.815-2.07-.785l-.515.068c-.497.131-.964.386-1.234.771-.817 1.063-.546 2.857.391 3.594.946.8 2.333 1.008 2.518 1.774.169.728-.307 1.043-.805 1.051-.704.01-1.147-.382-1.506-1.051l-1.249.719c.164.383.382.695.618.879 1.116.883 3.137.87 3.854-.193.247-.37.341-.81.377-1.287l-.004-.002z"/>
      </svg>
    );
  }

  // JSON
  if (language === "json" || ext === "json") {
    return (
      <svg className="w-4 h-4 text-yellow-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 6h4v4H4zM4 14h4v4H4zM12 6h8M12 10h6M12 14h8M12 18h6" />
      </svg>
    );
  }

  // Markdown
  if (language === "markdown" || ext === "md") {
    return (
      <svg className="w-4 h-4 text-slate-400" viewBox="0 0 24 24" fill="currentColor">
        <path d="M22 4H2v16h20V4zM7 15V9h2l2 3 2-3h2v6h-2v-4l-2 3-2-3v4H7zm10 0v-4h-2l3-3 3 3h-2v4h-2z"/>
      </svg>
    );
  }

  // YAML/TOML
  if (["yaml", "yml", "toml"].includes(language) || ["yaml", "yml", "toml"].includes(ext || "")) {
    return (
      <svg className="w-4 h-4 text-orange-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
      </svg>
    );
  }

  // HTML
  if (language === "html" || ext === "html" || ext === "htm") {
    return (
      <svg className="w-4 h-4 text-orange-500" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 17.56l-4.67-1.3 4.67 5.74 4.67-5.74-4.67 1.3zm8-12.56H4l1.63 14.22L12 22l6.37-2.78L20 5z"/>
      </svg>
    );
  }

  // CSS
  if (language === "css" || ext === "css") {
    return (
      <svg className="w-4 h-4 text-blue-500" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4 3l1.78 17.13L12 22l6.22-1.87L20 3H4zm14.22 5.22H8.12l.22 2.67h9.66l-.67 6.67L12 19l-5.33-1.44-.33-4.45h2.67l.11 2.22 2.89.67 2.89-.67.33-3.56H6.44L5.78 5.78h12.44v2.44z"/>
      </svg>
    );
  }

  // Default file icon
  return (
    <svg className="w-4 h-4 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

// Folder icon
function FolderIcon({ expanded }: { expanded: boolean }) {
  if (expanded) {
    return (
      <svg className="w-4 h-4 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
        <path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V6h5.17l2 2H20v10z"/>
      </svg>
    );
  }
  return (
    <svg className="w-4 h-4 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
      <path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/>
    </svg>
  );
}

// Build tree structure from flat file list
function buildTree(files: ExportFile[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];
  const folderMap = new Map<string, FileTreeNode>();

  // Sort files by path
  const sortedFiles = [...files].sort((a, b) => a.path.localeCompare(b.path));

  for (const file of sortedFiles) {
    const parts = file.path.split("/");
    let currentPath = "";

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      const parentPath = currentPath;
      currentPath = currentPath ? `${currentPath}/${part}` : part;

      if (isFile) {
        // Add file node
        const fileNode: FileTreeNode = {
          path: file.path,
          name: part,
          depth: i,
          isFolder: false,
          language: file.language,
          size: file.size,
          sha256: file.sha256,
          truncated: file.truncated,
        };

        if (parentPath) {
          const parent = folderMap.get(parentPath);
          if (parent) {
            parent.children = parent.children || [];
            parent.children.push(fileNode);
          }
        } else {
          root.push(fileNode);
        }
      } else {
        // Add folder node if not exists
        if (!folderMap.has(currentPath)) {
          const folderNode: FileTreeNode = {
            path: currentPath,
            name: part,
            depth: i,
            isFolder: true,
            children: [],
          };

          folderMap.set(currentPath, folderNode);

          if (parentPath) {
            const parent = folderMap.get(parentPath);
            if (parent) {
              parent.children = parent.children || [];
              parent.children.push(folderNode);
            }
          } else {
            root.push(folderNode);
          }
        }
      }
    }
  }

  return root;
}

// Flatten tree for rendering
function flattenTree(
  nodes: FileTreeNode[],
  expandedFolders: Set<string>,
  filterText: string
): FileTreeNode[] {
  const result: FileTreeNode[] = [];
  const filterLower = filterText.toLowerCase();

  function traverse(nodes: FileTreeNode[], depth: number) {
    for (const node of nodes) {
      // Filter check
      if (filterText && !node.path.toLowerCase().includes(filterLower)) {
        // For folders, check if any children match
        if (node.isFolder && node.children) {
          const hasMatchingChild = node.children.some(
            (child) => child.path.toLowerCase().includes(filterLower) ||
              (child.isFolder && child.children?.some((gc) => gc.path.toLowerCase().includes(filterLower)))
          );
          if (!hasMatchingChild) continue;
        } else {
          continue;
        }
      }

      result.push({ ...node, depth });

      if (node.isFolder && node.children && expandedFolders.has(node.path)) {
        traverse(node.children, depth + 1);
      }
    }
  }

  traverse(nodes, 0);
  return result;
}

export default function FileTree({
  files,
  selectedPath,
  onSelectFile,
  isLoading,
  entrypoints = [],
}: FileTreeProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());

  // Create a set for fast entrypoint lookup
  const entrypointSet = useMemo(() => new Set(entrypoints), [entrypoints]);

  // Build tree structure
  const tree = useMemo(() => buildTree(files), [files]);

  // Reset to fully collapsed whenever a new file set is loaded
  useEffect(() => {
    setExpandedFolders(new Set());
  }, [files]);

  // Flatten tree for rendering
  const flatNodes = useMemo(
    () => flattenTree(tree, expandedFolders, searchQuery),
    [tree, expandedFolders, searchQuery]
  );

  // Toggle folder expansion
  const toggleFolder = useCallback((path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full" style={{ color: "var(--text-muted)" }}>
        <svg className="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Loading files...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search input */}
      <div className="p-2 border-b" style={{ borderColor: "var(--border-default)" }}>
        <div className="relative">
          <svg
            className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: "var(--text-muted)" }}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            placeholder="Search files..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-sm rounded focus:outline-none focus:border-[var(--border-active)]"
            style={{
              backgroundColor: "var(--bg-tertiary)",
              border: "1px solid var(--border-default)",
              color: "var(--text-primary)"
            }}
          />
        </div>
      </div>

      {/* File count */}
      <div
        className="px-2 py-1 text-xs border-b"
        style={{ color: "var(--text-muted)", borderColor: "var(--border-default)" }}
      >
        {flatNodes.filter((n) => !n.isFolder).length} files
        {searchQuery && ` matching "${searchQuery}"`}
      </div>

      {/* File list */}
      <div className="flex-1 overflow-y-auto">
        {flatNodes.length === 0 ? (
          <div
            className="flex items-center justify-center h-full text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            {searchQuery ? "No files match your search" : "No files"}
          </div>
        ) : (
          <div className="py-1">
            {flatNodes.map((node) => {
              const isSelected = selectedPath === node.path;
              const isEntrypoint = !node.isFolder && entrypointSet.has(node.path);
              const paddingLeft = 8 + node.depth * 16;

              return (
                <button
                  key={node.path}
                  style={{
                    paddingLeft,
                    backgroundColor: isSelected ? "rgba(139, 148, 158, 0.12)" : "transparent",
                    color: isSelected
                      ? "var(--text-primary)"
                      : isEntrypoint
                      ? "#4ade80"
                      : "var(--text-secondary)"
                  }}
                  onClick={() => {
                    if (node.isFolder) {
                      toggleFolder(node.path);
                    } else {
                      onSelectFile(node.path);
                    }
                  }}
                  className="w-full text-left flex items-center gap-2 pr-2 py-1 text-sm transition-colors hover:bg-[var(--bg-tertiary)]"
                >
                  {node.isFolder ? (
                    <>
                      <svg
                        className={`w-3 h-3 transition-transform ${
                          expandedFolders.has(node.path) ? "rotate-90" : ""
                        }`}
                        style={{ color: "var(--text-muted)" }}
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path d="M6 6L14 10L6 14V6Z" />
                      </svg>
                      <FolderIcon expanded={expandedFolders.has(node.path)} />
                    </>
                  ) : (
                    <>
                      <span className="w-3" />
                      <FileIcon language={node.language || ""} path={node.path} />
                    </>
                  )}
                  <span className="truncate flex-1">{node.name}</span>
                  {isEntrypoint && (
                    <span
                      className="flex-shrink-0 px-1.5 py-0.5 text-[10px] rounded font-medium"
                      style={{ backgroundColor: "rgba(74, 222, 128, 0.2)", color: "#4ade80" }}
                      title="Entrypoint"
                    >
                      entry
                    </span>
                  )}
                  {node.truncated && (
                    <span
                      className="flex-shrink-0 w-2 h-2 rounded-full"
                      style={{ backgroundColor: "var(--accent-warning)" }}
                      title="Truncated"
                    />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
