"""Generic retry runtime wrapper for v2.1."""

from __future__ import annotations

import asyncio
import random
from typing import Any, Awaitable, Callable

from agent_compiler.models.ir import RetrySpec


def classify_retry_reason(error: Exception) -> str:
    text = str(error).lower()
    if "timeout" in text:
        return "timeout"
    if "rate limit" in text or "429" in text:
        return "rate_limit"
    if "5xx" in text or "503" in text or "502" in text or "500" in text:
        return "5xx"
    return "unknown"


async def run_with_retry(
    fn: Callable[[], Awaitable[Any]],
    retry_spec: RetrySpec,
    *,
    on_attempt: Callable[[int, str], Awaitable[None]] | None = None,
) -> Any:
    """Run an async fn with retry policy."""
    last_error: Exception | None = None
    attempts = max(1, retry_spec.max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            reason = classify_retry_reason(exc)
            if on_attempt is not None:
                await on_attempt(attempt, reason)
            should_retry = reason in retry_spec.retry_on or "any" in retry_spec.retry_on
            if attempt >= attempts or not should_retry:
                break
            delay = retry_spec.backoff_ms / 1000.0
            if retry_spec.jitter:
                delay = max(0.0, delay * (0.5 + random.random()))
            await asyncio.sleep(delay)
    raise last_error if last_error is not None else RuntimeError("Retry attempts exhausted")
