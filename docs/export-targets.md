# Export Targets

Forge exports IR v2 flows as standalone Python projects.

## Available targets

| Target | Surface | Typical use |
|---|---|---|
| `langgraph` | CLI | LangGraph-based orchestration |
| `runtime` | CLI | Smallest dependency footprint |
| `api_server` | HTTP | Run behind an HTTP interface |
| `aws-ecs` | HTTP + Terraform | Deploy on AWS ECS/Fargate |

## How to choose

1. Use `runtime` for minimal local or controlled deployments.
2. Use `langgraph` if you specifically want LangGraph orchestration.
3. Use `api_server` when the export must expose an HTTP API.
4. Use `aws-ecs` when the target environment is AWS ECS.

## Common output

Every export includes:

- generated agent modules
- runtime code
- tests
- `.env.example`
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `ir.json`

## HTTP targets

`api_server` and `aws-ecs` expose a FastAPI server on port `8080`.

Typical endpoints:

- `GET /health`
- `GET /healthz`
- `GET /ready`
- `GET /readyz`
- `GET /metrics`
- `POST /run`

## Runtime console support

Exports also include the internal observability server used by the Forge runtime
console. Default port: `9090`.

See [Runtime Console](./RUNTIME_CONSOLE.md).
