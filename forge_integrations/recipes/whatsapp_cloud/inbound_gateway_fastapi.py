"""Optional inbound webhook gateway example for WhatsApp Cloud API.

This file is a reference scaffold. In production, add signature validation.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request

from forge_integrations.shared.env import require_env
from forge_integrations.shared.http import request_json

app = FastAPI(title="WhatsApp Inbound Gateway")


def _extract_first_text(payload: dict[str, Any]) -> tuple[str, str]:
    entries = payload.get("entry") or []
    if not entries:
        return "", ""
    changes = (entries[0] or {}).get("changes") or []
    if not changes:
        return "", ""
    value = (changes[0] or {}).get("value") or {}
    messages = value.get("messages") or []
    if not messages:
        return "", ""
    msg = messages[0] or {}
    text = ((msg.get("text") or {}).get("body") or "").strip()
    sender = str(msg.get("from") or "").strip()
    return text, sender


@app.get("/webhooks/whatsapp")
async def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
) -> Any:
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="invalid_mode")
    verify_token = require_env("WHATSAPP_VERIFY_TOKEN")
    if hub_token != verify_token:
        raise HTTPException(status_code=403, detail="invalid_verify_token")
    return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge


@app.post("/webhooks/whatsapp")
async def receive_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()
    text, sender = _extract_first_text(payload)
    if not text:
        return {"ok": True, "skipped": True}

    runtime_url = require_env("FORGE_RUNTIME_INVOKE_URL")
    runtime_token = require_env("RUNTIME_API_TOKEN")
    normalized = {
        "input": text,
        "session_id": f"wa:{sender}",
        "metadata": {"channel": "whatsapp_cloud", "sender": sender},
    }
    _ = request_json(
        method="POST",
        url=runtime_url,
        headers={"Authorization": f"Bearer {runtime_token}"},
        json_body=normalized,
        timeout_s=float(os.environ.get("WHATSAPP_INGRESS_TIMEOUT_S", "8") or "8"),
        max_retries=int(os.environ.get("WHATSAPP_INGRESS_RETRIES", "1") or "1"),
    )
    return {"ok": True, "accepted": True}

