"""WhatsApp Cloud API outbound tool recipe."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from forge_integrations.shared.env import require_env
from forge_integrations.shared.http import request_json
from forge_integrations.shared.schemas import load_schema, validate_payload

_DIR = Path(__file__).resolve().parent
_INPUT_SCHEMA = load_schema(_DIR / "schemas" / "whatsapp_send_message.input.json")
_OUTPUT_SCHEMA = load_schema(_DIR / "schemas" / "whatsapp_send_message.output.json")


def run(args: dict[str, Any]) -> dict[str, Any]:
    """Send WhatsApp text message through Meta Cloud API."""
    validate_payload(schema=_INPUT_SCHEMA, payload=args, context="whatsapp_send_message input")

    access_token = require_env("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = require_env("WHATSAPP_PHONE_NUMBER_ID")
    api_version = os.environ.get("WHATSAPP_API_VERSION", "v20.0").strip() or "v20.0"
    timeout_s = float(os.environ.get("WHATSAPP_TIMEOUT_S", "10") or "10")
    max_retries = int(os.environ.get("WHATSAPP_MAX_RETRIES", "2") or "2")

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": args["to"],
        "type": "text",
        "text": {"body": args["text"], "preview_url": bool(args.get("preview_url", False))},
    }
    response = request_json(
        method="POST",
        url=f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json_body=payload,
        timeout_s=timeout_s,
        max_retries=max_retries,
    )

    messages = response.get("messages") or []
    message_id = ""
    if isinstance(messages, list) and messages:
        message_id = str((messages[0] or {}).get("id", ""))
    if not message_id:
        raise RuntimeError(f"WhatsApp API missing message id: {response}")

    output: dict[str, Any] = {
        "ok": True,
        "message_id": message_id,
        "provider": "whatsapp_cloud",
        "raw": response,
    }
    validate_payload(schema=_OUTPUT_SCHEMA, payload=output, context="whatsapp_send_message output")
    return output

