import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import EvalSuiteEditor from "@/components/eval/EvalSuiteEditor";
import type { EvalCase } from "@/types/eval";

vi.mock("@/lib/evalsApi", () => ({
  createCase: vi.fn(),
  updateCase: vi.fn(),
  deleteCase: vi.fn(),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as evalsApi from "@/lib/evalsApi";

const BASE_CASE: EvalCase = {
  id: "case_1",
  suite_id: "suite_1",
  name: "Case A",
  description: "",
  input: { text: "hello" },
  expected: { output: "world" },
  assertions: [{ type: "contains", expected: "world", field: "output" }],
  tags: ["smoke"],
  created_at: new Date().toISOString(),
};

describe("EvalSuiteEditor case edit/delete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("updates an existing case and notifies parent refresh", async () => {
    const onCasesChanged = vi.fn();
    const updateCaseMock = vi.mocked(evalsApi.updateCase);
    updateCaseMock.mockResolvedValue({
      ...BASE_CASE,
      name: "Case B",
      input: { text: "updated" },
    });

    render(
      <EvalSuiteEditor
        suiteId="suite_1"
        cases={[BASE_CASE]}
        onCasesChanged={onCasesChanged}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const nameInput = screen.getByDisplayValue("Case A");
    fireEvent.change(nameInput, { target: { value: "Case B" } });

    const inputEditor = screen.getByDisplayValue((value) =>
      String(value).includes('"text": "hello"')
    );
    fireEvent.change(inputEditor, { target: { value: '{"text":"updated"}' } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(updateCaseMock).toHaveBeenCalledWith("case_1", {
        name: "Case B",
        input: { text: "updated" },
        expected: { output: "world" },
        assertions: [{ type: "contains", expected: "world", field: "output" }],
      });
      expect(onCasesChanged).toHaveBeenCalled();
    });
  });

  it("deletes a case and refreshes parent list", async () => {
    const onCasesChanged = vi.fn();
    const deleteCaseMock = vi.mocked(evalsApi.deleteCase);
    deleteCaseMock.mockResolvedValue();
    vi.stubGlobal("confirm", vi.fn(() => true));

    render(
      <EvalSuiteEditor
        suiteId="suite_1"
        cases={[BASE_CASE]}
        onCasesChanged={onCasesChanged}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Del" }));

    await waitFor(() => {
      expect(deleteCaseMock).toHaveBeenCalledWith("case_1");
      expect(onCasesChanged).toHaveBeenCalled();
    });
  });
});
