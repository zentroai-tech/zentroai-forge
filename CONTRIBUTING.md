# Contributing

Contributions should stay scoped, reproducible, and easy to review.

## Workflow

- Branch from `main`
- Use branch names such as `feat/*`, `fix/*`, `docs/*`, or `chore/*`
- Open a pull request back to `main`
- Document user-visible behavior changes

## Local checks

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

## Before opening a PR

- Do not commit populated `.env` files or credentials
- Keep generated artifacts and caches out of the diff
- Prefer small, reviewable commits
- Update docs when public behavior changes

## Security

If the change affects auth, credentials, MCP execution, exports, or filesystem
handling, mention it clearly in the PR description.
