# Runtime Console

The runtime console is the Forge UI page at `/runtime`. It connects to an
exported project's internal observability server, not the exported public API.

## Ports

| Server | Default port | Purpose |
|---|---|---|
| `runtime.server` | `9090` | Runtime console and observability |
| `api.py` | `8080` | Public HTTP API for HTTP export targets |

## Basic flow

1. Export a project from Forge
2. Unpack it locally
3. Create `.env` from `.env.example`
4. Start the internal server:

```bash
python -m runtime.server
```

5. Open `http://localhost:3000/runtime`

## Useful environment variables

| Variable | Purpose |
|---|---|
| `FORGE_OBS_PORT` | Internal server port |
| `FORGE_OBS_HOST` | Bind address |
| `FORGE_RUNTIME_CORS_ORIGINS` | Allowed frontend origins |
| `DEV_MODE` | Enables development-oriented endpoints |

## Verify

```bash
curl http://localhost:9090/healthz
```

Expected response:

```json
{"status":"ok"}
```

## Typical troubleshooting

- `Disconnected`: runtime server is down or wrong port
- `Failed to fetch`: bad base URL or missing CORS
- session endpoints blocked: enable `DEV_MODE=1`
- no metrics: verify `GET /metrics` on port `9090`
