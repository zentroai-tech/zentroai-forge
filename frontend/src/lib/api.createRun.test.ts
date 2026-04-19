import { afterEach, describe, expect, it, vi } from "vitest";
import { createRun } from "@/lib/api";

const RUN_RESPONSE = {
  id: "run_1",
  flow_id: "flow_1",
  status: "completed",
  input: {},
  output: {},
  error_message: null,
  started_at: null,
  finished_at: null,
  created_at: new Date().toISOString(),
  timeline: [],
};

describe("api.createRun", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends input only when no entrypoint is provided", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(RUN_RESPONSE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );

    await createRun("flow_1", { q: "hello" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(String(options?.body));
    expect(body).toEqual({ input: { q: "hello" } });
  });

  it("includes entrypoint when provided", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(RUN_RESPONSE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );

    await createRun("flow_1", { q: "hello" }, "secondary");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/flows/flow_1/runs");
    const body = JSON.parse(String(options?.body));
    expect(body).toEqual({ input: { q: "hello" }, entrypoint: "secondary" });
  });
});
