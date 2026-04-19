"use client";

/**
 * ToolsPanel — IR Browser panel showing all tool contracts referenced in the
 * current flow IR.
 *
 * For each tool it shows:
 *   - name + version + contract_only badge
 *   - description
 *   - input/output schemas (collapsible JSON)
 *   - network/data scope summary
 *   - auth type + secret ref
 *   - "Copy stub" button (copies the generated Python stub skeleton)
 *
 * The panel reads tool_name values from Tool nodes across all agents in the IR.
 * MCP tools (mcp:*) are shown with a special "MCP wildcard" badge.
 */

import { useMemo, useState } from "react";
import type { FlowIRv2 } from "@/types/agents";
import { Badge } from "@/components/ui";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ToolContractSummary {
  name: string;
  version: string;
  description: string;
  contract_only: boolean;
  auth_type: string;
  has_network_scope: boolean;
  has_data_scope: boolean;
}

interface ToolEntry {
  tool_name: string;
  locations: string[];           // e.g. ["agent 'toolsmith' node 'sql'"]
  is_mcp: boolean;
  contract: ToolContractSummary | null;  // null = not in registry
}

interface ToolsPanelProps {
  ir: FlowIRv2 | null;
  /** Optional: pre-fetched contract summaries from GET /tool-contracts */
  contracts?: ToolContractSummary[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MCP_PREFIX = "mcp:";

function isMcp(name: string): boolean {
  return name.startsWith(MCP_PREFIX);
}

/** Extract all tool_name values from TOOL nodes across all agents. */
function collectToolEntries(
  ir: FlowIRv2 | null,
  contractMap: Map<string, ToolContractSummary>
): ToolEntry[] {
  if (!ir) return [];

  const seen = new Map<string, string[]>(); // tool_name -> locations

  const agents = ir.agents ?? [];
  for (const agent of agents) {
    const nodes = agent.graph?.nodes ?? [];
    for (const node of nodes) {
      if (node.type !== "Tool") continue;
      const toolName = (node.params as Record<string, unknown>)?.tool_name;
      if (typeof toolName !== "string" || !toolName) continue;
      const loc = `agent '${agent.id}' node '${node.id}'`;
      const existing = seen.get(toolName) ?? [];
      existing.push(loc);
      seen.set(toolName, existing);
    }
  }

  // Also include global_tools
  const globalTools: string[] = (ir.resources as { global_tools?: string[] } | undefined)?.global_tools ?? [];
  for (const t of globalTools) {
    if (!seen.has(t)) seen.set(t, ["resources.global_tools"]);
  }

  const entries: ToolEntry[] = [];
  for (const [tool_name, locations] of Array.from(seen.entries())) {
    entries.push({
      tool_name,
      locations,
      is_mcp: isMcp(tool_name),
      contract: contractMap.get(tool_name) ?? null,
    });
  }

  // Sort: contract_only first, then alpha
  entries.sort((a, b) => {
    if (a.is_mcp !== b.is_mcp) return a.is_mcp ? 1 : -1;
    const aContract = a.contract?.contract_only ? 0 : 1;
    const bContract = b.contract?.contract_only ? 0 : 1;
    if (aContract !== bContract) return aContract - bContract;
    return a.tool_name.localeCompare(b.tool_name);
  });

  return entries;
}

/** Generate a minimal Python stub skeleton for clipboard copy. */
function buildStubSkeleton(toolName: string): string {
  const fnName = toolName.replace(/-/g, "_").replace(/\./g, "_");
  return `from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class Input(BaseModel):
    # TODO: define fields matching the tool's input_schema
    pass


class Output(BaseModel):
    # TODO: define fields matching the tool's output_schema
    pass


async def ${fnName}(payload: dict[str, Any]) -> dict[str, Any]:
    """${toolName} — implement this tool."""
    data = Input.model_validate(payload)
    raise NotImplementedError("Implement ${toolName} in app/tools/impl/${toolName}.py")
`.replace(/\${fnName}/g, fnName).replace(/\${toolName}/g, toolName);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SchemaPreview({ schema }: { schema: unknown }) {
  const [open, setOpen] = useState(false);
  const preview = JSON.stringify(schema, null, 2);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[10px] underline"
        style={{ color: "var(--text-muted)" }}
      >
        {open ? "Hide schema" : "Show schema"}
      </button>
      {open && (
        <pre
          className="mt-1 max-h-32 overflow-auto rounded p-2 text-[10px]"
          style={{
            backgroundColor: "var(--bg-tertiary)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border-default)",
          }}
        >
          {preview}
        </pre>
      )}
    </div>
  );
}

function ToolCard({ entry }: { entry: ToolEntry }) {
  const [copied, setCopied] = useState(false);

  const handleCopyStub = async () => {
    try {
      await navigator.clipboard.writeText(buildStubSkeleton(entry.tool_name));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // noop
    }
  };

  const isUnknown = !entry.is_mcp && entry.contract === null;

  return (
    <div
      className="rounded-lg border p-3"
      style={{
        borderColor: isUnknown
          ? "#f59e0b55"
          : entry.contract?.contract_only
          ? "#3b82f655"
          : "var(--border-default)",
        backgroundColor: "var(--bg-secondary)",
      }}
    >
      {/* Header row */}
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
          {entry.tool_name}
        </span>
        {entry.is_mcp && <Badge label="MCP wildcard" color="#8b5cf6" />}
        {entry.contract?.contract_only && <Badge label="CONTRACT ONLY" color="#3b82f6" />}
        {isUnknown && <Badge label="UNKNOWN" color="#f59e0b" />}
        {entry.contract && !entry.contract.contract_only && !entry.is_mcp && (
          <Badge label="built-in" color="#10b981" />
        )}
        {entry.contract && (
          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
            v{entry.contract.version}
          </span>
        )}
      </div>

      {/* Description */}
      {entry.is_mcp ? (
        <p className="mb-1.5 text-[11px]" style={{ color: "var(--text-muted)" }}>
          MCP tool — resolved dynamically at runtime. No individual contract required.
        </p>
      ) : entry.contract ? (
        <p className="mb-1.5 text-[11px]" style={{ color: "var(--text-muted)" }}>
          {entry.contract.description}
        </p>
      ) : (
        <p className="mb-1.5 text-[11px]" style={{ color: "#f59e0b" }}>
          No contract registered for this tool. Add a ToolContract or use an mcp:&lt;name&gt; tool name.
        </p>
      )}

      {/* Scope badges */}
      {entry.contract && (
        <div className="mb-2 flex flex-wrap gap-1">
          {entry.contract.auth_type !== "none" && (
            <Badge label={`auth: ${entry.contract.auth_type}`} color="#f59e0b" />
          )}
          {entry.contract.has_network_scope && (
            <Badge label="network scope" color="#0ea5e9" />
          )}
          {entry.contract.has_data_scope && (
            <Badge label="data scope" color="#ec4899" />
          )}
        </div>
      )}

      {/* Locations */}
      <div className="mb-2">
        <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
          Used in:{" "}
          {entry.locations.map((loc, i) => (
            <span key={i} className="mr-1 font-mono">
              {loc}
              {i < entry.locations.length - 1 ? "," : ""}
            </span>
          ))}
        </span>
      </div>

      {/* Copy stub button */}
      {!entry.is_mcp && (
        <button
          type="button"
          onClick={handleCopyStub}
          className="btn-secondary text-[10px]"
        >
          {copied ? "Copied!" : "Copy stub"}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export default function ToolsPanel({ ir, contracts = [] }: ToolsPanelProps) {
  const contractMap = useMemo(() => {
    const m = new Map<string, ToolContractSummary>();
    for (const c of contracts) m.set(c.name, c);
    return m;
  }, [contracts]);

  const entries = useMemo(() => collectToolEntries(ir, contractMap), [ir, contractMap]);

  const contractOnlyCount = entries.filter((e) => e.contract?.contract_only).length;
  const unknownCount = entries.filter((e) => !e.is_mcp && e.contract === null).length;

  if (!ir) {
    return (
      <div className="flex items-center justify-center p-8 text-xs" style={{ color: "var(--text-muted)" }}>
        No IR loaded.
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center p-8 text-xs" style={{ color: "var(--text-muted)" }}>
        No Tool nodes found in this IR.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Summary bar */}
      <div
        className="flex flex-wrap items-center gap-3 border-b px-4 py-2"
        style={{ borderColor: "var(--border-default)" }}
      >
        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          {entries.length} tool{entries.length !== 1 ? "s" : ""} referenced
        </span>
        {contractOnlyCount > 0 && (
          <Badge label={`${contractOnlyCount} contract-only`} color="#3b82f6" />
        )}
        {unknownCount > 0 && (
          <Badge label={`${unknownCount} unknown`} color="#f59e0b" />
        )}
      </div>

      {/* Tool list */}
      <div className="flex-1 overflow-auto p-4">
        <div className="flex flex-col gap-3">
          {entries.map((entry) => (
            <ToolCard key={entry.tool_name} entry={entry} />
          ))}
        </div>

        {/* Contract-only notice */}
        {contractOnlyCount > 0 && (
          <div
            className="mt-4 rounded-lg border p-3 text-[11px]"
            style={{
              borderColor: "#3b82f655",
              backgroundColor: "#3b82f611",
              color: "var(--text-secondary)",
            }}
          >
            <strong>Contract-only tools</strong> have typed stubs and schemas but require external
            implementation. On export, Forge generates{" "}
            <code className="font-mono">app/tools/impl/&lt;tool&gt;.py</code> and{" "}
            <code className="font-mono">app/tools/contracts/&lt;tool&gt;.json</code> for each one.
            Fill in the stubs before running the exported project.
          </div>
        )}
      </div>
    </div>
  );
}
