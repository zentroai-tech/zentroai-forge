# telegram_send_message

Outbound Telegram Bot API tool recipe.

## Env vars

- `TELEGRAM_BOT_TOKEN` (required)
- `TELEGRAM_DEFAULT_CHAT_ID` (optional fallback)
- `TELEGRAM_TIMEOUT_S` (optional, default `10`)
- `TELEGRAM_MAX_RETRIES` (optional, default `2`)

## Files in this recipe

- `tool.py`
- `schemas/telegram_send_message.input.json`
- `schemas/telegram_send_message.output.json`
- `tests/test_contract.py`
- `tests/test_security.py`

## Copy into exported repo

- Tool: `tools/telegram_send_message.py`
- Schemas:
  - `runtime/schemas/tools/telegram_send_message.input.json`
  - `runtime/schemas/tools/telegram_send_message.output.json`
- Register in: `runtime/tools/registry.py`
- Allowlist in: `settings.py` (`FLOW_POLICIES["tool_allowlist"]`)
