"""Database connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.config import get_settings

settings = get_settings()

# Configure async engine with proper settings for SQLite/aiosqlite
# - Use StaticPool for SQLite to ensure single connection reuse
# - connect_args with check_same_thread=False required for SQLite async
is_sqlite = "sqlite" in settings.database_url

engine_kwargs = {
    "echo": settings.debug,
}

if is_sqlite:
    # SQLite requires special handling for async
    engine_kwargs["poolclass"] = StaticPool
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(
    settings.database_url,
    **engine_kwargs,
)


def get_engine() -> AsyncEngine:
    """Get the database engine instance."""
    return engine


async def init_db() -> None:
    """Initialize the database, creating all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session (for FastAPI dependency injection)."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session as a context manager.

    Use this when not using FastAPI dependency injection.
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
