from __future__ import annotations

import pytest

from forge_integrations.recipes.whatsapp_cloud import tool


def test_whatsapp_fails_without_env(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    with pytest.raises(RuntimeError):
        tool.run({"to": "15551234567", "text": "hello"})


def test_whatsapp_fails_without_message_id(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")

    def fake_request_json(**kwargs):
        return {"messages": []}

    monkeypatch.setattr(tool, "request_json", fake_request_json)
    with pytest.raises(RuntimeError):
        tool.run({"to": "15551234567", "text": "hello"})

