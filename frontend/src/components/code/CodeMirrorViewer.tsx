"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { EditorState, Extension } from "@codemirror/state";
import { EditorView, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection, highlightActiveLine, keymap } from "@codemirror/view";
import { defaultHighlightStyle, syntaxHighlighting, indentOnInput, bracketMatching, foldGutter, foldKeymap } from "@codemirror/language";
import { oneDark } from "@codemirror/theme-one-dark";
import toast from "react-hot-toast";

// Language imports (loaded dynamically based on file type)
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { yaml } from "@codemirror/lang-yaml";
import { StreamLanguage } from "@codemirror/language";
import { toml } from "@codemirror/legacy-modes/mode/toml";

interface CodeMirrorViewerProps {
  content: string;
  language: string;
  path: string;
  truncated?: boolean;
  originalSize?: number;
  isLoading?: boolean;
  error?: string;
}

type MarkdownPreviewTheme = "night" | "paper";

const MARKDOWN_PREVIEW_THEMES: Record<
  MarkdownPreviewTheme,
  {
    label: string;
    canvas: string;
    panel: string;
    border: string;
    text: string;
    muted: string;
    heading: string;
    link: string;
    codeBg: string;
    inlineCodeBg: string;
    quoteBorder: string;
  }
> = {
  night: {
    label: "Night",
    canvas: "linear-gradient(180deg, #1a1a1d 0%, #141418 100%)",
    panel: "#1c1c21",
    border: "#34343a",
    text: "#d4d4d8",
    muted: "#a1a1aa",
    heading: "#f1f1f3",
    link: "#7dd3fc",
    codeBg: "linear-gradient(90deg, #2a2a2f 0%, #2e2e33 100%)",
    inlineCodeBg: "rgba(250, 204, 21, 0.1)",
    quoteBorder: "#60a5fa",
  },
  paper: {
    label: "Paper",
    canvas: "linear-gradient(180deg, #eef2f7 0%, #e2e8f0 100%)",
    panel: "#f8fafc",
    border: "#cbd5e1",
    text: "#1e293b",
    muted: "#475569",
    heading: "#0f172a",
    link: "#0369a1",
    codeBg: "#e2e8f0",
    inlineCodeBg: "rgba(14, 116, 144, 0.14)",
    quoteBorder: "#0ea5e9",
  },
};

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInlineMarkdown(text: string): string {
  const escaped = escapeHtml(text);

  return escaped
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function highlightCodeLine(line: string, languageHint: string): string {
  const language = (languageHint || "").toLowerCase();
  const escaped = escapeHtml(line);

  const placeholders: string[] = [];
  let working = escaped;

  const stash = (value: string): string => {
    const token = `@@TOK${placeholders.length}@@`;
    placeholders.push(value);
    return token;
  };

  // Preserve strings/comments first so keyword replacement doesn't touch them.
  working = working.replace(/(&quot;.*?&quot;|&#39;.*?&#39;)/g, (m) => stash(`<span class="tok-string">${m}</span>`));
  working = working.replace(/(#[^\n]*)/g, (m) => stash(`<span class="tok-comment">${m}</span>`));

  if (["python", "py", ""].includes(language)) {
    const pyKeywords = /\b(import|from|as|def|class|return|if|else|elif|for|while|try|except|with|await|async|in|pass)\b/g;
    const pyBuiltins = /\b(print|len|range|dict|list|str|int|float|bool|None|True|False)\b/g;
    working = working.replace(pyKeywords, '<span class="tok-keyword">$1</span>');
    working = working.replace(pyBuiltins, '<span class="tok-builtin">$1</span>');
  } else if (["bash", "sh", "zsh", "shell"].includes(language)) {
    const shKeywords = /\b(if|then|else|fi|for|in|do|done|case|esac|function|export)\b/g;
    const shBuiltins = /\b(echo|cd|pwd|ls|cat|grep|awk|sed|python|npm|node)\b/g;
    working = working.replace(shKeywords, '<span class="tok-keyword">$1</span>');
    working = working.replace(shBuiltins, '<span class="tok-builtin">$1</span>');
  }

  working = working.replace(/@@TOK(\d+)@@/g, (_, i) => placeholders[Number(i)] || "");
  return working;
}

function renderMarkdownToHtml(markdownContent: string): string {
  const lines = markdownContent.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let inCodeBlock = false;
  let inUnorderedList = false;
  let inOrderedList = false;
  let codeLanguage = "";
  let index = 0;

  const closeLists = () => {
    if (inUnorderedList) {
      html.push("</ul>");
      inUnorderedList = false;
    }
    if (inOrderedList) {
      html.push("</ol>");
      inOrderedList = false;
    }
  };

  const isTableSeparator = (line: string): boolean => (
    /^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(line)
  );

  const splitTableRow = (row: string): string[] => {
    const normalized = row.trim().replace(/^\|/, "").replace(/\|$/, "");
    return normalized.split("|").map((cell) => cell.trim());
  };

  while (index < lines.length) {
    const line = lines[index];
    const fenceMatch = line.match(/^```(\w+)?\s*$/);
    if (fenceMatch) {
      closeLists();
      if (!inCodeBlock) {
        codeLanguage = fenceMatch[1] || "";
        html.push(`<pre><code class="language-${escapeHtml(codeLanguage)}">`);
        inCodeBlock = true;
      } else {
        html.push("</code></pre>");
        inCodeBlock = false;
        codeLanguage = "";
      }
      index += 1;
      continue;
    }

    if (inCodeBlock) {
      html.push(`${highlightCodeLine(line, codeLanguage)}\n`);
      index += 1;
      continue;
    }

    const nextLine = lines[index + 1] ?? "";
    if (line.includes("|") && isTableSeparator(nextLine)) {
      closeLists();
      const headers = splitTableRow(line);
      html.push("<table><thead><tr>");
      headers.forEach((header) => {
        html.push(`<th>${renderInlineMarkdown(header)}</th>`);
      });
      html.push("</tr></thead><tbody>");

      index += 2;
      while (index < lines.length) {
        const tableLine = lines[index];
        if (!tableLine.trim() || !tableLine.includes("|")) break;

        const cells = splitTableRow(tableLine);
        html.push("<tr>");
        cells.forEach((cell) => {
          html.push(`<td>${renderInlineMarkdown(cell)}</td>`);
        });
        html.push("</tr>");
        index += 1;
      }

      html.push("</tbody></table>");
      continue;
    }

    if (!line.trim()) {
      closeLists();
      html.push("");
      index += 1;
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      closeLists();
      const level = headingMatch[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      index += 1;
      continue;
    }

    const ulMatch = line.match(/^\s*[-*+]\s+(.+)$/);
    if (ulMatch) {
      if (!inUnorderedList) {
        if (inOrderedList) {
          html.push("</ol>");
          inOrderedList = false;
        }
        html.push("<ul>");
        inUnorderedList = true;
      }
      html.push(`<li>${renderInlineMarkdown(ulMatch[1])}</li>`);
      index += 1;
      continue;
    }

    const olMatch = line.match(/^\s*\d+\.\s+(.+)$/);
    if (olMatch) {
      if (!inOrderedList) {
        if (inUnorderedList) {
          html.push("</ul>");
          inUnorderedList = false;
        }
        html.push("<ol>");
        inOrderedList = true;
      }
      html.push(`<li>${renderInlineMarkdown(olMatch[1])}</li>`);
      index += 1;
      continue;
    }

    const quoteMatch = line.match(/^\s*>\s?(.+)$/);
    if (quoteMatch) {
      closeLists();
      html.push(`<blockquote>${renderInlineMarkdown(quoteMatch[1])}</blockquote>`);
      index += 1;
      continue;
    }

    closeLists();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
    index += 1;
  }

  if (inCodeBlock) {
    html.push("</code></pre>");
  }
  closeLists();

  return html.join("\n");
}

// Detect language from file path extension
function detectLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "";
  const extensionMap: Record<string, string> = {
    py: "python",
    js: "javascript",
    ts: "typescript",
    jsx: "jsx",
    tsx: "tsx",
    json: "json",
    md: "markdown",
    html: "html",
    htm: "html",
    css: "css",
    yaml: "yaml",
    yml: "yaml",
    toml: "toml",
    txt: "text",
  };
  return extensionMap[ext] || "text";
}

function getLanguageExtension(language: string, path: string): Extension | null {
  // Use provided language or detect from path
  const lang = language || detectLanguageFromPath(path);
  if (!lang) return null;

  switch (lang.toLowerCase()) {
    case "python":
    case "py":
      return python();
    case "javascript":
    case "js":
      return javascript();
    case "typescript":
    case "ts":
      return javascript({ typescript: true });
    case "jsx":
      return javascript({ jsx: true });
    case "tsx":
      return javascript({ jsx: true, typescript: true });
    case "json":
      return json();
    case "markdown":
    case "md":
      return markdown();
    case "html":
      return html();
    case "css":
      return css();
    case "yaml":
    case "yml":
      return yaml();
    case "toml":
      return StreamLanguage.define(toml);
    default:
      return null;
  }
}

export default function CodeMirrorViewer({
  content,
  language,
  path,
  truncated,
  originalSize,
  isLoading,
  error,
}: CodeMirrorViewerProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<"code" | "preview">("code");
  const [previewTheme, setPreviewTheme] = useState<MarkdownPreviewTheme>("night");

  const detectedLanguage = language || detectLanguageFromPath(path);
  const isMarkdown = ["markdown", "md"].includes(detectedLanguage.toLowerCase());

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy");
    }
  }, [content]);

  useEffect(() => {
    setViewMode(isMarkdown ? "preview" : "code");
  }, [isMarkdown, path]);

  useEffect(() => {
    if (!editorRef.current || isLoading || error || (isMarkdown && viewMode === "preview")) return;

    // Clean up previous editor
    if (viewRef.current) {
      viewRef.current.destroy();
      viewRef.current = null;
    }

    // Build extensions
    const extensions: Extension[] = [
      lineNumbers(),
      highlightActiveLineGutter(),
      highlightSpecialChars(),
      drawSelection(),
      indentOnInput(),
      bracketMatching(),
      highlightActiveLine(),
      foldGutter(),
      keymap.of(foldKeymap),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      oneDark,
      EditorState.readOnly.of(true),
      EditorView.editable.of(false),
      EditorView.theme({
        "&": {
          height: "100%",
          fontSize: "13px",
        },
        ".cm-scroller": {
          overflow: "auto",
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
        },
        ".cm-content": {
          padding: "8px 0",
        },
        ".cm-gutters": {
          backgroundColor: "#1e1e1e",
          borderRight: "1px solid #333",
        },
      }),
    ];

    // Add language support (with fallback to path-based detection)
    const langExt = getLanguageExtension(language, path);
    if (langExt) {
      extensions.push(langExt);
    }

    // Create editor state
    const state = EditorState.create({
      doc: content,
      extensions,
    });

    // Create editor view
    const view = new EditorView({
      state,
      parent: editorRef.current,
    });

    viewRef.current = view;

    return () => {
      view.destroy();
    };
  }, [content, language, path, isLoading, error, isMarkdown, viewMode]);

  const displayLanguage = detectedLanguage;
  const markdownHtml = isMarkdown ? renderMarkdownToHtml(content) : "";
  const selectedTheme = MARKDOWN_PREVIEW_THEMES[previewTheme];

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: "var(--bg-primary)" }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2 border-b"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-default)" }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            className="text-sm font-mono truncate"
            style={{ color: "var(--text-secondary)" }}
            title={path}
          >
            {path}
          </span>
          {truncated && (
            <span
              className="flex-shrink-0 px-2 py-0.5 text-xs rounded"
              style={{ backgroundColor: "rgba(234, 179, 8, 0.2)", color: "#facc15" }}
            >
              Truncated
            </span>
          )}
          <span
            className="flex-shrink-0 px-2 py-0.5 text-xs rounded"
            style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
          >
            {displayLanguage}
          </span>
          {isMarkdown && (
            <div
              className="flex items-center rounded p-0.5"
              style={{ backgroundColor: "var(--bg-tertiary)" }}
            >
              <button
                onClick={() => setViewMode("code")}
                className="px-2 py-1 text-xs rounded transition-colors"
                style={viewMode === "code"
                  ? { backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }
                  : { color: "var(--text-muted)" }}
              >
                Code
              </button>
              <button
                onClick={() => setViewMode("preview")}
                className="px-2 py-1 text-xs rounded transition-colors"
                style={viewMode === "preview"
                  ? { backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }
                  : { color: "var(--text-muted)" }}
              >
                Preview
              </button>
            </div>
          )}
          {isMarkdown && viewMode === "preview" && (
            <select
              value={previewTheme}
              onChange={(e) => setPreviewTheme(e.target.value as MarkdownPreviewTheme)}
              className="text-xs rounded px-2 py-1 focus:outline-none"
              style={{
                backgroundColor: "var(--bg-tertiary)",
                border: "1px solid var(--border-default)",
                color: "var(--text-secondary)",
              }}
              title="Markdown preview theme"
            >
              {Object.entries(MARKDOWN_PREVIEW_THEMES).map(([value, theme]) => (
                <option key={value} value={value}>
                  Theme: {theme.label}
                </option>
              ))}
            </select>
          )}
        </div>
        <button
          onClick={handleCopy}
          disabled={isLoading || !!error}
          className="flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors disabled:opacity-50 hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-muted)" }}
          title="Copy to clipboard"
        >
          {copied ? (
            <>
              <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Copied
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy
            </>
          )}
        </button>
      </div>

      {/* Truncation warning */}
      {truncated && originalSize && (
        <div
          className="px-4 py-2 border-b text-sm"
          style={{
            backgroundColor: "rgba(234, 179, 8, 0.1)",
            borderColor: "rgba(234, 179, 8, 0.2)",
            color: "#facc15"
          }}
        >
          Preview truncated ({Math.round(content.length / 1024)}KB shown of {Math.round(originalSize / 1024)}KB).
          Download ZIP to view full file.
        </div>
      )}

      {/* Editor container */}
      <div className="flex-1 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="flex items-center gap-3" style={{ color: "var(--text-muted)" }}>
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading file...
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center p-8">
              <div
                className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center"
                style={{ backgroundColor: "var(--bg-tertiary)" }}
              >
                <svg className="w-8 h-8" style={{ color: "var(--text-muted)" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <p style={{ color: "var(--text-secondary)" }}>{error}</p>
            </div>
          </div>
        ) : isMarkdown && viewMode === "preview" ? (
          <div
            className="h-full overflow-auto px-6 py-5"
            style={{ background: selectedTheme.canvas }}
          >
            <article
              className="rounded-xl border p-8 shadow-sm [&>h1]:text-4xl [&>h1]:font-semibold [&>h1]:tracking-tight [&>h1]:mb-5 [&>h2]:text-3xl [&>h2]:font-semibold [&>h2]:mt-8 [&>h2]:mb-4 [&>h3]:text-2xl [&>h3]:font-semibold [&>h3]:mt-7 [&>h3]:mb-3 [&>p]:mb-4 [&>ul]:list-disc [&>ul]:pl-6 [&>ul]:mb-4 [&>ol]:list-decimal [&>ol]:pl-6 [&>ol]:mb-4 [&>blockquote]:border-l-4 [&>blockquote]:pl-4 [&>blockquote]:italic [&>blockquote]:my-4 [&_pre]:rounded-md [&_pre]:p-5 [&_pre]:overflow-x-auto [&_pre]:my-4 [&_pre]:text-sm [&_code]:font-mono [&_code]:text-sm [&_p_code]:px-1.5 [&_p_code]:py-0.5 [&_p_code]:rounded [&_a]:underline [&_a]:underline-offset-2 [&_table]:w-full [&_table]:border-collapse [&_table]:my-5 [&_th]:text-left [&_th]:font-semibold [&_th]:px-3 [&_th]:py-2 [&_th]:border [&_td]:px-3 [&_td]:py-2 [&_td]:border"
              style={{
                backgroundColor: selectedTheme.panel,
                borderColor: selectedTheme.border,
                color: selectedTheme.text,
                ["--md-heading" as string]: selectedTheme.heading,
                ["--md-muted" as string]: selectedTheme.muted,
                ["--md-link" as string]: selectedTheme.link,
                ["--md-code-bg" as string]: selectedTheme.codeBg,
                ["--md-inline-code-bg" as string]: selectedTheme.inlineCodeBg,
                ["--md-quote" as string]: selectedTheme.quoteBorder,
                ["--md-border" as string]: selectedTheme.border,
              }}
              dangerouslySetInnerHTML={{ __html: markdownHtml }}
            />
            <style jsx>{`
              article :global(h1),
              article :global(h2),
              article :global(h3),
              article :global(h4),
              article :global(h5),
              article :global(h6) {
                color: var(--md-heading);
              }
              article :global(h2) {
                border-bottom: 1px solid var(--md-border);
                padding-bottom: 0.35rem;
              }
              article :global(a) {
                color: var(--md-link);
              }
              article :global(pre) {
                background: var(--md-code-bg);
                border: 1px solid var(--md-border);
              }
              article :global(p code),
              article :global(li code),
              article :global(blockquote code),
              article :global(td code),
              article :global(th code) {
                background: var(--md-inline-code-bg);
              }
              article :global(blockquote) {
                border-left-color: var(--md-quote);
                color: var(--md-muted);
              }
              article :global(th),
              article :global(td) {
                border-color: var(--md-border);
              }
              article :global(thead th) {
                background: var(--md-code-bg);
                color: var(--md-heading);
              }
              article :global(.tok-keyword) {
                color: #5fb4ff;
              }
              article :global(.tok-builtin) {
                color: #2dd4bf;
              }
              article :global(.tok-string) {
                color: #f2b179;
              }
              article :global(.tok-comment) {
                color: #8b8b96;
              }
            `}</style>
          </div>
        ) : (
          <div ref={editorRef} className="h-full" />
        )}
      </div>
    </div>
  );
}
