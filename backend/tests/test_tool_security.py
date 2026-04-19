"""Tests for tool security helpers and MCP guardrails."""

from __future__ import annotations

import pytest
import agent_compiler.services.mcp_client as mcp_client

from agent_compiler.config import get_settings
from agent_compiler.runtime.context import ExecutionContext
from agent_compiler.services.mcp_client import (
    MCPError,
    is_mcp_tool,
    resolve_mcp_target,
    call_mcp_tool,
)
from agent_compiler.services.tool_security import is_tool_allowed, safe_calculator_eval


def test_is_tool_allowed_patterns() -> None:
    assert is_tool_allowed("calculator", ["calculator"])
    assert is_tool_allowed("mcp:pubmed.search", ["mcp:*"])
    assert is_tool_allowed("anything", ["*"])
    assert not is_tool_allowed("shell", ["calculator", "search"])


def test_safe_calculator_eval_allows_arithmetic_only() -> None:
    assert safe_calculator_eval("2 + 3 * 4") == 14
    assert safe_calculator_eval("(2 + 3) * 4") == 20
    with pytest.raises(ValueError):
        safe_calculator_eval("__import__('os').system('whoami')")


def test_resolve_mcp_target_from_tool_name_prefix() -> None:
    target_name, args, cfg = resolve_mcp_target(
        tool_name="mcp:pubmed.search",
        tool_input={"query": "tp53"},
        tool_config={"mcp_server": {"command": "dummy"}},
    )
    assert target_name == "pubmed.search"
    assert args == {"query": "tp53"}
    assert cfg["command"] == "dummy"


@pytest.mark.asyncio
async def test_call_mcp_tool_fails_when_disabled() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    original = settings.mcp_enabled
    settings.mcp_enabled = False
    try:
        with pytest.raises(MCPError):
            await call_mcp_tool(
                tool_name="mcp:test.tool",
                tool_input={},
                tool_config={"mcp_server": {"command": "python", "args": ["-V"]}},
            )
    finally:
        settings.mcp_enabled = original
        get_settings.cache_clear()


def test_mcp_detection() -> None:
    assert is_mcp_tool("mcp:tool")
    assert is_mcp_tool("tool", {"mcp_server": {"command": "node"}})
    assert not is_mcp_tool("calculator", {})


@pytest.mark.asyncio
async def test_call_mcp_tool_reuses_session_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    original_enabled = settings.mcp_enabled
    settings.mcp_enabled = True
    cache: dict[str, object] = {}
    created = {"count": 0}

    async def fake_get_or_create_session(**kwargs):  # type: ignore[no-untyped-def]
        session_cache = kwargs["session_cache"]
        assert session_cache is cache
        key = "session-key"
        if key not in session_cache:
            created["count"] += 1
            session_cache[key] = object()
        return session_cache[key]

    async def fake_call_with_session(session, target_name, arguments):  # type: ignore[no-untyped-def]
        return {"ok": True, "name": target_name, "args": arguments, "session_id": id(session)}

    async def fake_close_session(_session):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(mcp_client, "_get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(mcp_client, "_call_with_session", fake_call_with_session)
    monkeypatch.setattr(mcp_client, "_close_session", fake_close_session)

    tool_cfg = {"mcp_server": {"command": "dummy"}}
    try:
        r1 = await call_mcp_tool(
            tool_name="mcp:pubmed.search",
            tool_input={"query": "tp53"},
            tool_config=tool_cfg,
            session_cache=cache,
        )
        r2 = await call_mcp_tool(
            tool_name="mcp:pubmed.search",
            tool_input={"query": "egfr"},
            tool_config=tool_cfg,
            session_cache=cache,
        )
        assert created["count"] == 1
        assert r1["result"]["session_id"] == r2["result"]["session_id"]
    finally:
        settings.mcp_enabled = original_enabled
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_execution_context_closes_pooled_sessions() -> None:
    closed = {"count": 0}

    class FakeSession:
        async def close(self) -> None:
            closed["count"] += 1

    context = ExecutionContext()
    context.mcp_sessions["a"] = FakeSession()
    context.mcp_sessions["b"] = FakeSession()
    await context.close_external_resources()

    assert closed["count"] == 2
    assert context.mcp_sessions == {}
