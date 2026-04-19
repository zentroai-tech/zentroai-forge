# Development Guide

## Prerequisites

- Python `3.11+`
- Node.js `20+`
- npm `10+`

## Local setup

### Backend

```bash
cd backend
py -3.11 -m venv .venv
pip install --upgrade pip
pip install -e ".[dev]"
```

### Frontend

```bash
cd frontend
npm ci
cp .env.example .env.local
```

## Run

Backend:

```bash
cd backend
py -3.11 -m uvicorn agent_compiler.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm run dev
```

## Quality checks

Backend:

```bash
cd backend
py -3.11 -m ruff check src tests
py -3.11 -m pytest tests -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run type-check
npm test
```

## Conventions

- IR contract: only IR v2 payloads are supported
- Backend domain logic lives in `backend/src/agent_compiler/services/`
- HTTP layer lives in `backend/src/agent_compiler/routers/`
- Frontend state is centered in `frontend/src/lib/store.ts`
- Frontend API boundary is `frontend/src/lib/api.ts`

## Common pitfalls

1. Wrong Python version causes backend dependency issues.
2. Missing provider API keys causes run failures.
3. Wrong `NEXT_PUBLIC_API_BASE_URL` points the frontend at the wrong backend.
4. Enabling `AGENT_COMPILER_API_KEY` without sending `X-API-Key` blocks requests.
5. Tight MCP allowlists can block tool execution unexpectedly.
6. Old local DB state can conflict with newer flow assumptions.
