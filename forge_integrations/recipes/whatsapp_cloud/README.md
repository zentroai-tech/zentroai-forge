# whatsapp_send_message

WhatsApp Cloud API outbound tool recipe + optional inbound gateway example.

## Env vars

- `WHATSAPP_ACCESS_TOKEN` (required)
- `WHATSAPP_PHONE_NUMBER_ID` (required)
- `WHATSAPP_API_VERSION` (optional, default `v20.0`)
- `WHATSAPP_TIMEOUT_S` (optional, default `10`)
- `WHATSAPP_MAX_RETRIES` (optional, default `2`)

Optional inbound gateway env vars:
- `WHATSAPP_VERIFY_TOKEN`
- `FORGE_RUNTIME_INVOKE_URL`
- `RUNTIME_API_TOKEN`

## Copy into exported repo

- Tool: `tools/whatsapp_send_message.py`
- Schemas:
  - `runtime/schemas/tools/whatsapp_send_message.input.json`
  - `runtime/schemas/tools/whatsapp_send_message.output.json`
- Register in: `runtime/tools/registry.py`
- Allowlist in: `settings.py` (`FLOW_POLICIES["tool_allowlist"]`)
