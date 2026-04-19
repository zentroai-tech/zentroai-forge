import { create } from "zustand";
import type {
  ApprovalRequest,
  SessionMemorySnapshot,
  ToolHealth,
  RuntimeRunStep,
  RuntimeRunSummary,
  RuntimeToolSpec,
} from "@/lib/api/runtime";

type RunMap = Record<string, RuntimeRunSummary>;
type StepsMap = Record<string, RuntimeRunStep[]>;

interface RuntimeRunsState {
  currentRunId: string | null;
  runsById: RunMap;
  stepsByRunId: StepsMap;
  toolsCatalog: RuntimeToolSpec[];
  approvalsBySessionId: Record<string, ApprovalRequest[]>;
  replayByRunId: Record<string, string>;
  toolHealth: ToolHealth["tools"];
  sessionMemoryBySessionId: Record<string, SessionMemorySnapshot>;
  setCurrentRunId: (runId: string | null) => void;
  upsertRun: (run: RuntimeRunSummary) => void;
  setRunSteps: (runId: string, steps: RuntimeRunStep[]) => void;
  setToolsCatalog: (tools: RuntimeToolSpec[]) => void;
  setApprovalsForSession: (sessionId: string, approvals: ApprovalRequest[]) => void;
  setReplayMapping: (runId: string, replayRunId: string) => void;
  setToolHealth: (health: ToolHealth["tools"]) => void;
  setSessionMemory: (sessionId: string, snapshot: SessionMemorySnapshot) => void;
}

export const useRuntimeRunsStore = create<RuntimeRunsState>((set) => ({
  currentRunId: null,
  runsById: {},
  stepsByRunId: {},
  toolsCatalog: [],
  approvalsBySessionId: {},
  replayByRunId: {},
  toolHealth: {},
  sessionMemoryBySessionId: {},
  setCurrentRunId: (runId) => set({ currentRunId: runId }),
  upsertRun: (run) =>
    set((state) => ({
      runsById: {
        ...state.runsById,
        [run.run_id]: run,
      },
    })),
  setRunSteps: (runId, steps) =>
    set((state) => ({
      stepsByRunId: {
        ...state.stepsByRunId,
        [runId]: steps,
      },
    })),
  setToolsCatalog: (tools) => set({ toolsCatalog: tools }),
  setApprovalsForSession: (sessionId, approvals) =>
    set((state) => ({
      approvalsBySessionId: {
        ...state.approvalsBySessionId,
        [sessionId]: approvals,
      },
    })),
  setReplayMapping: (runId, replayRunId) =>
    set((state) => ({
      replayByRunId: {
        ...state.replayByRunId,
        [runId]: replayRunId,
      },
    })),
  setToolHealth: (health) => set({ toolHealth: health }),
  setSessionMemory: (sessionId, snapshot) =>
    set((state) => ({
      sessionMemoryBySessionId: {
        ...state.sessionMemoryBySessionId,
        [sessionId]: snapshot,
      },
    })),
}));
