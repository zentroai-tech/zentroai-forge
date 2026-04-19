"""Telegram outbound tool recipe."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from forge_integrations.shared.env import require_env
from forge_integrations.shared.http import request_json
from forge_integrations.shared.schemas import load_schema, validate_payload

_DIR = Path(__file__).resolve().parent
_INPUT_SCHEMA = load_schema(_DIR / "schemas" / "telegram_send_message.input.json")
_OUTPUT_SCHEMA = load_schema(_DIR / "schemas" / "telegram_send_message.output.json")


def run(args: dict[str, Any]) -> dict[str, Any]:
    """Send a Telegram message via Bot API."""
    validate_payload(schema=_INPUT_SCHEMA, payload=args, context="telegram_send_message input")
    token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = str(args.get("chat_id") or os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")).strip()
    if not chat_id:
        raise RuntimeError("chat_id is required (input.chat_id or TELEGRAM_DEFAULT_CHAT_ID)")

    timeout_s = float(os.environ.get("TELEGRAM_TIMEOUT_S", "10") or "10")
    max_retries = int(os.environ.get("TELEGRAM_MAX_RETRIES", "2") or "2")
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": args["text"],
    }
    if "parse_mode" in args:
        payload["parse_mode"] = args["parse_mode"]
    if "disable_web_page_preview" in args:
        payload["disable_web_page_preview"] = args["disable_web_page_preview"]

    response = request_json(
        method="POST",
        url=f"https://api.telegram.org/bot{token}/sendMessage",
        json_body=payload,
        timeout_s=timeout_s,
        max_retries=max_retries,
    )

    if not bool(response.get("ok")):
        raise RuntimeError(f"Telegram API returned non-ok response: {response}")

    result = response.get("result") or {}
    output: dict[str, Any] = {
        "ok": True,
        "message_id": result.get("message_id", ""),
        "provider": "telegram",
        "raw": response,
    }
    validate_payload(schema=_OUTPUT_SCHEMA, payload=output, context="telegram_send_message output")
    return output

