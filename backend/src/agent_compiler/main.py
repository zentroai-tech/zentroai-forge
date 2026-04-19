"""FastAPI application entry point."""

import argparse
import hmac
import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent_compiler import __version__
from agent_compiler.config import get_settings
from agent_compiler.database import get_engine, init_db
from agent_compiler.middleware import APIKeyAuthMiddleware, RequestLoggingMiddleware
from agent_compiler.migrations import run_migrations
from agent_compiler.observability.logging import get_logger, setup_logging
from agent_compiler.observability.tracing import setup_tracing
from agent_compiler.routers import agents_router, exports_router, flows_router, runs_router
from agent_compiler.routers.credentials import router as credentials_router
from agent_compiler.routers.debug import router as debug_router
from agent_compiler.routers.evals import router as evals_router
from agent_compiler.routers.gitops import exports_gitops_router
from agent_compiler.routers.gitops import router as gitops_router
from agent_compiler.routers.integrations_library import router as integrations_library_router
from agent_compiler.routers.logs import install_sse_log_handler
from agent_compiler.routers.logs import router as logs_router
from agent_compiler.routers.providers import router as providers_router
from agent_compiler.routers.templates import projects_router
from agent_compiler.routers.templates import router as templates_router
from agent_compiler.routers.tools import router as tool_contracts_router
from agent_compiler.services.cleanup_service import (
    CleanupService,
    start_cleanup_task,
    stop_cleanup_task,
)

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    setup_logging(debug=settings.debug, json_logs=settings.json_logs)
    install_sse_log_handler()
    setup_tracing()

    # Log auth status
    if settings.is_auth_enabled:
        logger.info("API key authentication enabled")
    else:
        forge_env = os.environ.get("FORGE_ENV", "development").lower()
        if forge_env in {"prod", "production"}:
            raise RuntimeError(
                "AGENT_COMPILER_API_KEY is required when FORGE_ENV=production. "
                "Auth cannot be disabled in production mode."
            )
        logger.warning(
            "API key authentication DISABLED - set AGENT_COMPILER_API_KEY for production"
        )

    # Log encryption status
    if settings.is_encryption_enabled:
        logger.info("Credential encryption enabled (FORGE_MASTER_KEY set)")
    else:
        logger.warning(
            "Credential encryption DISABLED - set FORGE_MASTER_KEY to enable "
            "credential storage. Generate with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    # Log MCP status
    if settings.mcp_enabled:
        if not settings.mcp_allowed_commands:
            logger.warning(
                "MCP enabled with EMPTY mcp_allowed_commands — any command may be spawned. "
                "Set AGENT_COMPILER_MCP_ALLOWED_COMMANDS in production."
            )
        if not settings.mcp_allowed_tools:
            logger.warning(
                "MCP enabled with EMPTY mcp_allowed_tools — any tool may be called. "
                "Set AGENT_COMPILER_MCP_ALLOWED_TOOLS in production."
            )

    # Initialize database
    await init_db()

    # Run migrations
    engine = get_engine()
    try:
        await run_migrations(engine)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

    # Start background cleanup task
    start_cleanup_task(interval_hours=1.0)

    # Run initial cleanup
    try:
        cleanup_service = CleanupService()
        await cleanup_service.cleanup_expired_exports()
    except Exception as e:
        logger.warning(f"Initial cleanup failed: {e}")

    yield

    # Shutdown
    stop_cleanup_task()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Build, run, and export AI agent flows",
    version=__version__,
    lifespan=lifespan,
)

# Add request logging middleware (first, so it wraps everything)
app.add_middleware(RequestLoggingMiddleware)

# Add API key auth middleware
app.add_middleware(APIKeyAuthMiddleware)

# CORS middleware with configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
    expose_headers=["Content-Disposition"],
)

# Include routers
app.include_router(flows_router)
app.include_router(runs_router)
app.include_router(exports_router)
app.include_router(evals_router)
app.include_router(gitops_router)
app.include_router(exports_gitops_router)
app.include_router(templates_router)
app.include_router(projects_router)
app.include_router(credentials_router)
app.include_router(debug_router)
app.include_router(logs_router)
app.include_router(providers_router)
app.include_router(agents_router)
app.include_router(integrations_library_router)
app.include_router(tool_contracts_router)


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Kubernetes/ECS-style health check endpoint."""
    return {"status": "ok", "service": "agent-compiler"}


@app.get("/engines")
async def list_engines() -> dict[str, Any]:
    """List available engine adapters."""
    from agent_compiler.adapters.registry import get_registry

    registry = get_registry()
    available = registry.get_available()

    return {
        "available": available,
        "default": settings.default_engine,
        "all_adapters": ["langchain", "llamaindex"],
    }


# =============================================================================
# Admin endpoints (protected by API key)
# =============================================================================


async def _require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency that enforces API key auth when auth is enabled.

    Used for GET admin endpoints which are not caught by the write-only
    middleware path.
    """
    if not settings.is_auth_enabled:
        return
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

@app.post("/admin/cleanup")
async def trigger_cleanup() -> dict[str, Any]:
    """Manually trigger export cleanup.

    Requires API key authentication.
    """
    cleanup_service = CleanupService()
    stats = await cleanup_service.cleanup_expired_exports()
    return {
        "status": "completed",
        "stats": stats,
    }


@app.get("/admin/migrations", dependencies=[Depends(_require_api_key)])
async def migration_status() -> dict[str, Any]:
    """Get migration status.

    Requires API key authentication.
    """
    from agent_compiler.migrations import get_migration_status

    engine = get_engine()
    status = await get_migration_status(engine)
    return status


@app.get("/admin/config", dependencies=[Depends(_require_api_key)])
async def get_config() -> dict[str, Any]:
    """Get current configuration (sanitized).

    Requires API key authentication.
    """
    return {
        "app_name": settings.app_name,
        "debug": settings.debug,
        "default_engine": settings.default_engine,
        "cors_allow_origins": settings.cors_allow_origins,
        "export_ttl_hours": settings.export_ttl_hours,
        "auth_enabled": settings.is_auth_enabled,
        "require_auth_for_reads": settings.require_auth_for_reads,
        "otel_enabled": settings.otel_enabled,
    }


def cli() -> None:
    """CLI entry point for running the server."""
    parser = argparse.ArgumentParser(description="Agent Compiler Backend")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    if args.debug:
        import os
        os.environ["AGENT_COMPILER_DEBUG"] = "true"

    uvicorn.run(
        "agent_compiler.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    cli()
