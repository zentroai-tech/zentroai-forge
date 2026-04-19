"use client";

import type { AgentSpec } from "@/types/agents";
import { Button, Tooltip } from "@/components/ui";

interface AgentSelectorProps {
  agents: AgentSpec[];
  selectedAgentId: string | null;
  onSelect: (agentId: string) => void;
  onAddAgent: () => void;
  onEditAgent?: (agentId: string) => void;
  onDeleteAgent?: (agentId: string) => void;
}

export default function AgentSelector({
  agents,
  selectedAgentId,
  onSelect,
  onAddAgent,
  onEditAgent,
  onDeleteAgent,
}: AgentSelectorProps) {
  return (
    <div className="flex min-w-0 items-start gap-2 px-3 py-2.5 bg-[var(--bg-secondary)] border-b border-[var(--border-default)]">
      <div className="flex min-w-0 flex-1 items-start gap-2">
        <span className="shrink-0 text-xs text-[var(--text-muted)] mt-1">Agent:</span>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1 pr-1">
          {agents.map((agent) => (
            <div key={agent.id} className="flex shrink-0 items-center gap-1">
              <button
                onClick={() => onSelect(agent.id)}
                className={`btn-pill text-xs ${selectedAgentId === agent.id ? "active" : ""}`}
              >
                {agent.name}
                <span className="ml-1 text-[var(--text-muted)] text-[10px]">
                  ({agent.graph.nodes.length})
                </span>
              </button>
              {selectedAgentId === agent.id && (
                <>
                  <Tooltip content="Edit agent" side="bottom">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onEditAgent?.(agent.id)}
                    >
                      Edit
                    </Button>
                  </Tooltip>
                  <Tooltip content="Delete agent" side="bottom">
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => onDeleteAgent?.(agent.id)}
                    >
                      Del
                    </Button>
                  </Tooltip>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
      <Tooltip content="Add Agent" side="bottom">
        <Button
          variant="ghost"
          size="sm"
          onClick={onAddAgent}
          className="shrink-0"
        >
          + Agent
        </Button>
      </Tooltip>
    </div>
  );
}
