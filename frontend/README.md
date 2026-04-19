# Frontend

Next.js frontend for Zentro Forge.

## Stack

- Next.js `14`
- React `18`
- TypeScript
- React Flow
- Zustand
- Vitest

## Run locally

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`.

## Environment

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API base URL |

Default local backend: `http://localhost:8000`

## Main areas

- `src/app/`: app router pages
- `src/components/flow/`: editor, palette, inspector, agent UI
- `src/components/debugger/`: runs, timeline, replay, diff
- `src/components/eval/`: eval suites and results
- `src/components/code/`: export preview and file browser
- `src/lib/`: API client, stores, helpers
- `src/types/`: shared frontend types

## IR contract

The frontend edits and submits only IR v2 payloads.

Canonical frontend IR types:

- `src/types/agents.ts`
- `src/types/ir.ts`

## Commands

```bash
cd frontend
npm run lint
npm run type-check
npm test
```

Known local limitation: the login gate in `src/app/page.tsx` is only a UX gate,
not real backend authentication.
