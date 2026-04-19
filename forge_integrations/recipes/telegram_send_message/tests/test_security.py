from __future__ import annotations

import pytest

from forge_integrations.recipes.telegram_send_message import tool


def test_telegram_fails_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        tool.run({"chat_id": "42", "text": "hello"})


def test_telegram_fails_without_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.delenv("TELEGRAM_DEFAULT_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError):
        tool.run({"text": "hello"})

