import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import RunsList from "@/components/debugger/RunsList";
import { useFlowStore } from "@/lib/store";
import type { Flow } from "@/types/ir";

vi.mock("@/lib/api", () => ({
  listRuns: vi.fn(async () => []),
  createRun: vi.fn(),
  deleteAllRuns: vi.fn(async () => ({ deleted: 0 })),
}));
import * as api from "@/lib/api";

function buildFlow(overrides?: Partial<Flow>): Flow {
  return {
    id: "flow_1",
    name: "Flow",
    version: "1.0.0",
    description: "",
    ir_version: "2",
    engine_preference: "langchain",
    nodes: [],
    edges: [],
    agents: [
      {
        id: "main",
        name: "Main Agent",
        graph: { nodes: [], edges: [], root: "start" },
        llm: { provider: "auto", model: "gpt-4o-mini", temperature: 0.7, system_prompt: null },
        tools_allowlist: [],
        memory_namespace: "main_memory",
        budgets: { max_depth: 5 },
      },
    ],
    handoffs: [],
    entrypoints: [{ name: "main", agent_id: "main", description: "default" }],
    resources: { shared_memory_namespaces: [], global_tools: [], schema_contracts: {} },
    ...overrides,
  };
}

describe("RunsList v2 entrypoint behavior", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    useFlowStore.setState({
      currentFlow: null,
      selectedNodeId: null,
      selectedAgentId: null,
      hasUnsavedChanges: false,
      mcpServers: [],
    });
  });

  it("blocks run creation when v2 flow has no entrypoints", async () => {
    useFlowStore.setState({
      currentFlow: buildFlow({ entrypoints: [] }),
    });

    render(
      <RunsList
        flowId="flow_1"
        selectedRunId={null}
        onSelectRun={vi.fn()}
        initialShowNewRun={true}
      />
    );

    expect(await screen.findByText("No entrypoints configured. Open Entrypoints and create at least one.")).toBeInTheDocument();
    const runButton = screen.getByRole("button", { name: "Run" });
    expect(runButton).toBeDisabled();
    expect(api.createRun).not.toHaveBeenCalled();
  });

  it("sends selected entrypoint when creating v2 run", async () => {
    const createRunMock = vi.mocked(api.createRun);
    createRunMock.mockResolvedValue({
      id: "run_123",
      flow_id: "flow_1",
      status: "pending",
      input: {},
      output: null,
      error_message: null,
      started_at: null,
      finished_at: null,
      created_at: new Date().toISOString(),
      timeline: [],
    });

    useFlowStore.setState({
      currentFlow: buildFlow({
        entrypoints: [
          { name: "main", agent_id: "main", description: "default" },
          { name: "secondary", agent_id: "main", description: "secondary" },
        ],
      }),
    });

    const onSelectRun = vi.fn();
    render(
      <RunsList
        flowId="flow_1"
        selectedRunId={null}
        onSelectRun={onSelectRun}
        initialShowNewRun={true}
      />
    );

    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "secondary" },
    });
    fireEvent.change(screen.getByPlaceholderText('{"input": "Hello, how can you help me?"}'), {
      target: { value: '{"foo":"bar"}' },
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Run$/ })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Run$/ }));

    await waitFor(() => {
      expect(createRunMock).toHaveBeenCalledWith("flow_1", { foo: "bar" }, "secondary");
      expect(onSelectRun).toHaveBeenCalledWith("run_123");
    });
  });
});
