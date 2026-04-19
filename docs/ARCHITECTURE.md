# Architecture

Zentro Forge is a local-first system with three main layers:

1. Next.js frontend
2. FastAPI backend
3. Generated runtime/export projects

## High-level flow

```text
Frontend UI
  -> REST / SSE
Backend API
  -> DB, runtime, evals, exports, GitOps
Generated export
  -> standalone Python project
```

## Frontend

Main responsibilities:

- edit multi-agent flows
- configure agents, handoffs, policies, and tools
- launch runs, replay, evals, and exports
- inspect timeline, logs, and generated code

Main areas:

- `frontend/src/components/flow/`
- `frontend/src/components/debugger/`
- `frontend/src/components/eval/`
- `frontend/src/components/code/`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/store.ts`

## Backend

Main responsibilities:

- persist flows and versions
- execute runs and record timeline events
- validate IR and tool references
- manage eval suites and replay
- generate exports and GitOps jobs

Main areas:

- `backend/src/agent_compiler/routers/`
- `backend/src/agent_compiler/services/`
- `backend/src/agent_compiler/runtime/`
- `backend/src/agent_compiler/models/`

## Data model

Core persisted entities include:

- flows
- flow_versions
- runs
- steps
- agent_events
- step_artifacts
- exports
- credentials
- eval_suites
- eval_runs

## IR

The backend accepts only IR v2 payloads.

Core schema files:

- `backend/src/agent_compiler/models/ir.py`
- `backend/src/agent_compiler/models/ir_v2.py`

## Export pipeline

The export path is:

```text
Flow IR v2
  -> validation
  -> export preparation
  -> MultiAgentGenerator
  -> preview / zip / GitOps
```

Generated targets:

- `langgraph`
- `runtime`
- `api_server`
- `aws-ecs`
