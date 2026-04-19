import { beforeEach, describe, expect, it } from "vitest";
import { useFlowStore } from "@/lib/store";

describe("flow store v2", () => {
  beforeEach(() => {
    localStorage.clear();
    useFlowStore.setState({
      currentFlow: null,
      selectedNodeId: null,
      selectedAgentId: null,
      hasUnsavedChanges: false,
      mcpServers: [],
    });
  });

  it("creates new flows as ir v2 with default agent and entrypoint", () => {
    const store = useFlowStore.getState();
    store.createNewFlow("Test");

    const flow = useFlowStore.getState().currentFlow;
    expect(flow).not.toBeNull();
    expect(flow?.ir_version).toBe("2");
    expect(flow?.agents?.length).toBe(1);
    expect(flow?.entrypoints?.[0]?.name).toBe("main");
    expect(flow?.entrypoints?.[0]?.agent_id).toBe("main");
  });

  it("supports v2 agent and handoff CRUD constraints", () => {
    const store = useFlowStore.getState();
    store.createNewFlow("Test");

    const added = store.addAgent({ id: "researcher", name: "Researcher" });
    expect(added?.id).toBe("researcher");
    expect(useFlowStore.getState().currentFlow?.agents?.length).toBe(2);

    expect(
      store.addHandoff({
        from_agent_id: "main",
        to_agent_id: "researcher",
        mode: "delegate",
      })
    ).toBe(true);

    expect(
      store.addHandoff({
        from_agent_id: "main",
        to_agent_id: "researcher",
        mode: "delegate",
      })
    ).toBe(false);

    expect(
      store.addHandoff({
        from_agent_id: "main",
        to_agent_id: "main",
        mode: "delegate",
      })
    ).toBe(false);
  });

  it("removing an agent cleans handoffs and preserves at least one entrypoint", () => {
    const store = useFlowStore.getState();
    store.createNewFlow("Test");
    store.addAgent({ id: "writer", name: "Writer" });
    store.setEntrypoints([{ name: "secondary", agent_id: "writer", description: "Writer entrypoint" }]);
    store.addHandoff({
      from_agent_id: "main",
      to_agent_id: "writer",
      mode: "delegate",
    });

    const removed = store.removeAgent("writer");
    expect(removed).toBe(true);

    const flow = useFlowStore.getState().currentFlow;
    expect(flow?.agents?.map((a) => a.id)).toEqual(["main"]);
    expect(flow?.handoffs).toEqual([]);
    expect(flow?.entrypoints?.length).toBe(1);
    expect(flow?.entrypoints?.[0]?.name).toBe("main");
    expect(flow?.entrypoints?.[0]?.agent_id).toBe("main");
  });
});
