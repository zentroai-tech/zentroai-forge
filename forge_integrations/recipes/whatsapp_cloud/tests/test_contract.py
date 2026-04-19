from __future__ import annotations

from forge_integrations.recipes.whatsapp_cloud import tool


def test_whatsapp_contract_success(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")

    def fake_request_json(**kwargs):
        assert kwargs["method"] == "POST"
        return {"messages": [{"id": "wamid.abc"}]}

    monkeypatch.setattr(tool, "request_json", fake_request_json)
    out = tool.run({"to": "15551234567", "text": "hello"})
    assert out["ok"] is True
    assert out["message_id"] == "wamid.abc"

