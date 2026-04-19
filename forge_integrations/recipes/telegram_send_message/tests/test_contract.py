from __future__ import annotations

from forge_integrations.recipes.telegram_send_message import tool


def test_telegram_contract_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

    def fake_request_json(**kwargs):
        assert kwargs["method"] == "POST"
        return {"ok": True, "result": {"message_id": 123}}

    monkeypatch.setattr(tool, "request_json", fake_request_json)
    out = tool.run({"chat_id": "42", "text": "hello"})
    assert out["ok"] is True
    assert out["message_id"] == 123
    assert out["provider"] == "telegram"

