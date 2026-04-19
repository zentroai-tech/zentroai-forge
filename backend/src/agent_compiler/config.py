"""Configuration management for Agent Compiler."""

import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _get_env(key: str, default: Any) -> Any:
    """Get environment variable with AGENT_COMPILER_ prefix."""
    env_key = f"AGENT_COMPILER_{key}"
    value = os.environ.get(env_key)
    if value is None:
        return default
    # Type coercion
    if isinstance(default, bool):
        return value.lower() in ("true", "1", "yes")
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    if isinstance(default, Path):
        return Path(value)
    return value


def _get_list_env(key: str, default: list[str]) -> list[str]:
    """Get comma-separated list from environment variable."""
    env_key = f"AGENT_COMPILER_{key}"
    value = os.environ.get(env_key)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    """Application settings loaded from environment variables."""

    app_name: str = "Agent Compiler"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./agent_compiler.db"

    # Encryption master key for credentials (required for credential storage)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    forge_master_key: str = ""

    # Default engine preference
    default_engine: str = "langchain"

    # LLM defaults
    default_model: str = "gpt-3.5-turbo"
    default_temperature: float = 0.7

    # RAG defaults
    default_top_k: int = 5
    abstain_threshold: float = 0.3

    # Export settings
    export_temp_dir: Path = Path(tempfile.gettempdir()) / "agent_compiler_exports"
    export_ttl_hours: int = 24  # Cleanup exports older than this

    # CORS settings
    cors_allow_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    cors_allow_headers: list[str] = ["*"]

    # Security settings
    api_key: str = ""  # Empty = auth disabled (dev mode)
    api_key_header: str = "X-API-Key"
    require_auth_for_reads: bool = False  # Only require auth for writes by default
    enforce_v1_tool_allowlist: bool = True
    v1_tool_allowlist: list[str] = [
        "calculator",
        "datetime",
        "search",
        "web_search",
        "url_reader",
        "query_engine",
        "mcp:*",
    ]
    mcp_enabled: bool = False
    mcp_timeout_seconds: float = 20.0
    mcp_allowed_commands: list[str] = []  # empty => allow any command when MCP enabled
    mcp_allowed_tools: list[str] = []  # empty => allow any MCP tool name
    mcp_max_response_chars: int = 20000

    # Logging settings
    log_level: str = "INFO"
    json_logs: bool = False

    # OpenTelemetry
    otel_enabled: bool = False
    otel_service_name: str = "agent-compiler"
    otel_endpoint: str = ""

    def __init__(self, **data: Any) -> None:
        # Load from environment
        super().__init__(
            app_name=_get_env("APP_NAME", data.get("app_name", "Agent Compiler")),
            debug=_get_env("DEBUG", data.get("debug", False)),
            database_url=_get_env(
                "DATABASE_URL",
                data.get("database_url", "sqlite+aiosqlite:///./agent_compiler.db"),
            ),
            forge_master_key=os.environ.get("FORGE_MASTER_KEY", data.get("forge_master_key", "")),
            default_engine=_get_env("DEFAULT_ENGINE", data.get("default_engine", "langchain")),
            default_model=_get_env("DEFAULT_MODEL", data.get("default_model", "gpt-3.5-turbo")),
            default_temperature=_get_env(
                "DEFAULT_TEMPERATURE", data.get("default_temperature", 0.7)
            ),
            default_top_k=_get_env("DEFAULT_TOP_K", data.get("default_top_k", 5)),
            abstain_threshold=_get_env(
                "ABSTAIN_THRESHOLD", data.get("abstain_threshold", 0.3)
            ),
            export_temp_dir=_get_env(
                "EXPORT_TEMP_DIR",
                data.get("export_temp_dir", Path(tempfile.gettempdir()) / "agent_compiler_exports"),
            ),
            export_ttl_hours=_get_env(
                "EXPORT_TTL_HOURS", data.get("export_ttl_hours", 24)
            ),
            cors_allow_origins=_get_list_env(
                "CORS_ALLOW_ORIGINS",
                data.get("cors_allow_origins", [
                    "http://localhost:3000",
                    "http://localhost:5173",
                    "http://127.0.0.1:3000",
                    "http://127.0.0.1:5173",
                ]),
            ),
            cors_allow_credentials=_get_env(
                "CORS_ALLOW_CREDENTIALS", data.get("cors_allow_credentials", True)
            ),
            api_key=_get_env("API_KEY", data.get("api_key", "")),
            api_key_header=_get_env("API_KEY_HEADER", data.get("api_key_header", "X-API-Key")),
            require_auth_for_reads=_get_env(
                "REQUIRE_AUTH_FOR_READS", data.get("require_auth_for_reads", False)
            ),
            enforce_v1_tool_allowlist=_get_env(
                "ENFORCE_V1_TOOL_ALLOWLIST",
                data.get("enforce_v1_tool_allowlist", True),
            ),
            v1_tool_allowlist=_get_list_env(
                "V1_TOOL_ALLOWLIST",
                data.get(
                    "v1_tool_allowlist",
                    [
                        "calculator",
                        "datetime",
                        "search",
                        "web_search",
                        "url_reader",
                        "query_engine",
                        "mcp:*",
                    ],
                ),
            ),
            mcp_enabled=_get_env("MCP_ENABLED", data.get("mcp_enabled", False)),
            mcp_timeout_seconds=_get_env(
                "MCP_TIMEOUT_SECONDS",
                data.get("mcp_timeout_seconds", 20.0),
            ),
            mcp_allowed_commands=_get_list_env(
                "MCP_ALLOWED_COMMANDS",
                data.get("mcp_allowed_commands", []),
            ),
            mcp_allowed_tools=_get_list_env(
                "MCP_ALLOWED_TOOLS",
                data.get("mcp_allowed_tools", []),
            ),
            mcp_max_response_chars=_get_env(
                "MCP_MAX_RESPONSE_CHARS",
                data.get("mcp_max_response_chars", 20000),
            ),
            log_level=_get_env("LOG_LEVEL", data.get("log_level", "INFO")),
            json_logs=_get_env("JSON_LOGS", data.get("json_logs", False)),
            otel_enabled=_get_env("OTEL_ENABLED", data.get("otel_enabled", False)),
            otel_service_name=_get_env(
                "OTEL_SERVICE_NAME", data.get("otel_service_name", "agent-compiler")
            ),
            otel_endpoint=_get_env("OTEL_ENDPOINT", data.get("otel_endpoint", "")),
        )

    @property
    def is_auth_enabled(self) -> bool:
        """Check if API key auth is enabled."""
        return bool(self.api_key)

    @property
    def is_encryption_enabled(self) -> bool:
        """Check if credential encryption is configured."""
        return bool(self.forge_master_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
