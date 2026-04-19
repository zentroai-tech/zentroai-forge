"""MCP stdio client for tool execution with per-run session pooling."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from agent_compiler.config import get_settings
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.tool_security import is_tool_allowed

logger = get_logger(__name__)


class MCPError(RuntimeError):
    """Raised when an MCP call fails."""


class MCPStdioSession:
    """Persistent stdio MCP session for repeated tool calls."""

    def __init__(
        self,
        command: str,
        args: list[str],
        cwd: str | None,
        env: dict[str, str],
        timeout: float,
    ) -> None:
        self.command = command
        self.args = args
        self.cwd = cwd
        self.env = env
        self.timeout = timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()
        self._initialized = False


def is_mcp_tool(tool_name: str, tool_config: dict[str, Any] | None = None) -> bool:
    """Detect whether a tool should be routed through MCP."""
    if tool_name.startswith("mcp:"):
        return True
    config = tool_config or {}
    return bool(config.get("mcp_server") or config.get("mcp"))


def resolve_mcp_target(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Resolve MCP server config, target tool name, and call arguments."""
    config = tool_config or {}
    mcp = config.get("mcp_server") or config.get("mcp") or {}
    if not isinstance(mcp, dict):
        raise MCPError("Invalid MCP config; expected object in tool_config.mcp_server")

    target_name = mcp.get("tool_name") or config.get("mcp_tool_name")
    if not target_name:
        target_name = tool_name.split(":", 1)[1] if tool_name.startswith("mcp:") else ""
    if not target_name:
        raise MCPError("MCP tool name missing. Use tool_name='mcp:<name>' or mcp_server.tool_name")

    args = mcp.get("arguments")
    if args is None:
        args = tool_input
    if not isinstance(args, dict):
        raise MCPError("MCP arguments must be a JSON object")

    return target_name, args, mcp


def _validate_command(command: str) -> None:
    settings = get_settings()
    if not settings.mcp_enabled:
        raise MCPError("MCP is disabled. Set AGENT_COMPILER_MCP_ENABLED=true")

    allowed = settings.mcp_allowed_commands
    executable = os.path.basename(command)
    if allowed and command not in allowed and executable not in allowed:
        raise MCPError(
            f"MCP command '{command}' not allowed. Allowed commands: {allowed}"
        )


def _validate_tool_name(tool_name: str) -> None:
    settings = get_settings()
    if settings.mcp_allowed_tools and not is_tool_allowed(tool_name, settings.mcp_allowed_tools):
        raise MCPError(
            f"MCP tool '{tool_name}' not allowed. Allowed: {settings.mcp_allowed_tools}"
        )


def _format_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


async def _read_message(reader: asyncio.StreamReader) -> dict[str, Any]:
    content_length: int | None = None
    while True:
        line = await reader.readline()
        if not line:
            raise MCPError("MCP server closed stream")
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("ascii", errors="replace").strip()
        if decoded.lower().startswith("content-length:"):
            content_length = int(decoded.split(":", 1)[1].strip())
    if content_length is None:
        raise MCPError("Missing Content-Length in MCP response")
    body = await reader.readexactly(content_length)
    return json.loads(body.decode("utf-8"))


async def _rpc(
    writer: asyncio.StreamWriter,
    reader: asyncio.StreamReader,
    req_id: int,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        request["params"] = params
    writer.write(_format_message(request))
    await writer.drain()

    response = await _read_message(reader)
    if "error" in response:
        raise MCPError(f"MCP {method} failed: {response['error']}")
    return response.get("result", {})


def _make_session_cache_key(
    command: str,
    args: list[str],
    cwd: str | None,
    env: dict[str, str],
) -> str:
    """Create a deterministic cache key for MCP session reuse."""
    env_items = sorted((k, env[k]) for k in env.keys())
    return json.dumps(
        {
            "command": command,
            "args": args,
            "cwd": cwd or "",
            "env": env_items,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


async def _create_stdio_session(
    command: str,
    args: list[str],
    cwd: str | None,
    env: dict[str, str],
    timeout: float,
) -> MCPStdioSession:
    return MCPStdioSession(
        command=command,
        args=args,
        cwd=cwd,
        env=env,
        timeout=timeout,
    )


async def _ensure_started(session: MCPStdioSession) -> None:
    if session._proc and session._proc.returncode is None and session._initialized:
        return

    proc = await asyncio.create_subprocess_exec(
        session.command,
        *session.args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=session.cwd if session.cwd else None,
        env=session.env,
    )
    if proc.stdin is None or proc.stdout is None:
        raise MCPError("Failed to open MCP stdio streams")

    session._proc = proc
    session._reader = proc.stdout
    session._writer = proc.stdin
    session._initialized = False
    session._next_id = 1

    await asyncio.wait_for(
        _rpc(
            session._writer,
            session._reader,
            session._next_id,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "agent-compiler", "version": "0.1.0"},
            },
        ),
        timeout=session.timeout,
    )
    session._next_id += 1
    session._initialized = True


async def _call_with_session(
    session: MCPStdioSession,
    target_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    async with session._lock:
        await _ensure_started(session)
        assert session._writer is not None
        assert session._reader is not None
        req_id = session._next_id
        result = await asyncio.wait_for(
            _rpc(
                session._writer,
                session._reader,
                req_id,
                "tools/call",
                {"name": target_name, "arguments": arguments},
            ),
            timeout=session.timeout,
        )
        session._next_id += 1
        return result


async def _close_session(session: MCPStdioSession) -> None:
    proc = session._proc
    if proc is None or proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def _get_or_create_session(
    *,
    command: str,
    args: list[str],
    cwd: str | None,
    env: dict[str, str],
    timeout: float,
    session_cache: dict[str, MCPStdioSession] | None,
) -> MCPStdioSession:
    if session_cache is None:
        return await _create_stdio_session(command, args, cwd, env, timeout)

    key = _make_session_cache_key(command, args, cwd, env)
    existing = session_cache.get(key)
    if existing is not None:
        return existing

    created = await _create_stdio_session(command, args, cwd, env, timeout)
    session_cache[key] = created
    return created


async def call_mcp_tool(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    tool_config: dict[str, Any] | None = None,
    session_cache: dict[str, MCPStdioSession] | None = None,
) -> dict[str, Any]:
    """Invoke an MCP tool through a stdio server."""
    settings = get_settings()
    target_name, arguments, mcp = resolve_mcp_target(tool_name, tool_input, tool_config)
    _validate_tool_name(target_name)

    command = mcp.get("command")
    if not command or not isinstance(command, str):
        raise MCPError("Missing mcp_server.command")
    _validate_command(command)

    args = mcp.get("args", [])
    if not isinstance(args, list):
        raise MCPError("mcp_server.args must be a list")
    args = [str(a) for a in args]

    cwd = mcp.get("cwd")
    env = os.environ.copy()
    if isinstance(mcp.get("env"), dict):
        for k, v in mcp["env"].items():
            env[str(k)] = str(v)

    timeout = float(mcp.get("timeout_seconds", settings.mcp_timeout_seconds))
    logger.info("Calling MCP tool '%s' via command '%s'", target_name, command)
    pooled = session_cache is not None
    session = await _get_or_create_session(
        command=command,
        args=args,
        cwd=cwd if isinstance(cwd, str) and cwd else None,
        env=env,
        timeout=timeout,
        session_cache=session_cache,
    )
    try:
        result = await _call_with_session(session, target_name, arguments)
    except asyncio.TimeoutError as e:
        raise MCPError(f"MCP call timed out after {timeout}s") from e
    except Exception:
        # If this session came from pool and failed, drop/close it to avoid poisoning next calls.
        if session_cache is not None:
            try:
                key = _make_session_cache_key(
                    session.command, session.args, session.cwd, session.env
                )
                cached = session_cache.get(key)
                if cached is session:
                    session_cache.pop(key, None)
            except Exception:
                pass
            await _close_session(session)
        raise
    finally:
        if not pooled:
            await _close_session(session)

    raw = json.dumps(result, default=str)
    if len(raw) > settings.mcp_max_response_chars:
        raw = raw[: settings.mcp_max_response_chars] + "...(truncated)"
    return {
        "mcp": True,
        "tool_name": target_name,
        "result": result,
        "result_preview": raw,
    }


setattr(MCPStdioSession, "close", _close_session)
