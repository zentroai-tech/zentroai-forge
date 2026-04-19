"""Middleware for request handling, auth, and logging."""

import hmac
import time
import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from agent_compiler.config import get_settings
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

# Context variable for request ID correlation
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get current request ID from context."""
    return request_id_var.get()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request logging with timing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        request_id_var.set(request_id)

        # Record start time
        start_time = time.perf_counter()

        # Add request ID to response headers
        response = None
        error_detail = None

        try:
            response = await call_next(request)
        except Exception as e:
            error_detail = str(e)
            raise
        finally:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Get status code
            status_code = response.status_code if response else 500

            # Build log data
            log_data = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else "unknown",
            }

            # Add query params if present
            if request.query_params:
                log_data["query_params"] = dict(request.query_params)

            # Log based on status
            if status_code >= 500:
                logger.error(
                    f"[{request_id}] {request.method} {request.url.path} -> {status_code} ({duration_ms:.2f}ms)",
                    extra=log_data,
                )
            elif status_code >= 400:
                logger.warning(
                    f"[{request_id}] {request.method} {request.url.path} -> {status_code} ({duration_ms:.2f}ms)",
                    extra=log_data,
                )
            else:
                logger.info(
                    f"[{request_id}] {request.method} {request.url.path} -> {status_code} ({duration_ms:.2f}ms)",
                    extra=log_data,
                )

        # Add request ID to response headers
        if response:
            response.headers["X-Request-ID"] = request_id

        return response


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication on write endpoints."""

    # Endpoints that require authentication (write operations)
    PROTECTED_PATTERNS = [
        ("POST", "/flows"),
        ("PUT", "/flows/"),
        ("DELETE", "/flows/"),
        ("POST", "/flows/", "/export"),
        ("POST", "/flows/", "/runs"),
        ("POST", "/admin/"),
    ]

    # Always public endpoints
    PUBLIC_ENDPOINTS = [
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("GET", "/redoc"),
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()

        # If auth is disabled, pass through
        if not settings.is_auth_enabled:
            return await call_next(request)

        # Check if this is a public endpoint
        if self._is_public_endpoint(request):
            return await call_next(request)

        # Check if this endpoint requires auth
        requires_auth = self._requires_auth(request, settings)

        if requires_auth:
            # Get API key from header
            api_key = request.headers.get(settings.api_key_header)

            if not api_key:
                logger.warning(
                    f"Missing API key for {request.method} {request.url.path}",
                    extra={"client_ip": request.client.host if request.client else "unknown"},
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "API key required"},
                )

            if not hmac.compare_digest(api_key, settings.api_key):
                logger.warning(
                    f"Invalid API key for {request.method} {request.url.path}",
                    extra={"client_ip": request.client.host if request.client else "unknown"},
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid API key"},
                )

        return await call_next(request)

    def _is_public_endpoint(self, request: Request) -> bool:
        """Check if endpoint is always public."""
        for method, path in self.PUBLIC_ENDPOINTS:
            if request.method == method and request.url.path == path:
                return True
        return False

    def _requires_auth(self, request: Request, settings) -> bool:
        """Check if this endpoint requires authentication."""
        method = request.method
        path = request.url.path

        # Write operations always require auth if enabled
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            return True

        # Read operations only require auth if configured
        if method == "GET" and settings.require_auth_for_reads:
            # Exclude static/doc endpoints
            if not any(path.startswith(p) for p in ["/docs", "/openapi", "/redoc"]):
                return True

        return False
