"""Real-time log streaming via SSE."""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent_compiler.observability.logging import get_logger

router = APIRouter(prefix="/logs", tags=["logs"])
logger = get_logger(__name__)

# In-memory circular buffer of recent log entries + list of active subscribers
_log_buffer: deque[dict[str, Any]] = deque(maxlen=500)
_subscribers: list[asyncio.Queue] = []


class SSELogHandler(logging.Handler):
    """Python logging handler that pushes records into the SSE system."""

    def emit(self, record: logging.LogRecord):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }
        # Attach extras (run_id, node_id, etc.)
        for attr in ("run_id", "step_id", "node_id", "node_type"):
            val = getattr(record, attr, None)
            if val:
                entry[attr] = val

        _log_buffer.append(entry)
        for q in _subscribers:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass  # skip slow consumers


def install_sse_log_handler():
    """Install the SSE handler on the root agent_compiler logger."""
    root = logging.getLogger("agent_compiler")
    # Only install once
    if not any(isinstance(h, SSELogHandler) for h in root.handlers):
        handler = SSELogHandler()
        handler.setLevel(logging.DEBUG)
        root.addHandler(handler)


@router.get("/stream")
async def stream_logs(
    level: str = "INFO",
    run_id: str | None = None,
    node_id: str | None = None,
):
    """Stream backend logs via SSE with optional filters.

    Query params:
    - level: minimum log level (DEBUG, INFO, WARNING, ERROR)
    - run_id: filter by run ID
    - node_id: filter by node ID
    """
    min_level = getattr(logging, level.upper(), logging.INFO)
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.append(queue)

    async def event_generator():
        try:
            # Send recent buffer first
            for entry in list(_log_buffer):
                if _matches_filter(entry, min_level, run_id, node_id):
                    yield _format_sse(entry)

            # Stream new entries
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if _matches_filter(entry, min_level, run_id, node_id):
                        yield _format_sse(entry)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        finally:
            _subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/recent")
async def get_recent_logs(
    limit: int = 100,
    level: str = "INFO",
) -> list[dict[str, Any]]:
    """Get recent logs from the buffer."""
    min_level = getattr(logging, level.upper(), logging.INFO)
    entries = [
        e for e in list(_log_buffer)
        if _matches_filter(e, min_level, None, None)
    ]
    return entries[-limit:]


def _matches_filter(
    entry: dict[str, Any],
    min_level: int,
    run_id: str | None,
    node_id: str | None,
) -> bool:
    """Check if a log entry matches the given filters."""
    entry_level = getattr(logging, entry.get("level", "INFO"), logging.INFO)
    if entry_level < min_level:
        return False
    if run_id and entry.get("run_id") != run_id:
        return False
    if node_id and entry.get("node_id") != node_id:
        return False
    return True


def _format_sse(entry: dict[str, Any]) -> str:
    """Format a log entry as an SSE event."""
    data = json.dumps(entry, default=str)
    return f"data: {data}\n\n"
