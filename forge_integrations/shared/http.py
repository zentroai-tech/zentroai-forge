"""Small HTTP JSON wrapper with retries and explicit timeouts."""

from __future__ import annotations

import time
from typing import Any

import requests


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class HttpRequestError(RuntimeError):
    """Raised when an HTTP request fails after retries."""


def request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_s: float = 10.0,
    max_retries: int = 2,
    backoff_s: float = 0.4,
) -> dict[str, Any]:
    """Send an HTTP request and parse JSON response."""
    attempts = max(1, max_retries + 1)
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=json_body,
                timeout=timeout_s,
            )
            if response.status_code in RETRYABLE_STATUS and attempt < attempts - 1:
                time.sleep(backoff_s * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise HttpRequestError("Expected JSON object response.")
            return data
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(backoff_s * (attempt + 1))
                continue
            break

    raise HttpRequestError(f"HTTP request failed after retries: {last_error}")

