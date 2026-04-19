"""Simple migration runner for schema versioning.

This is a minimal migration system that tracks schema versions
and applies migrations in order. For more complex needs, consider
switching to Alembic.

Usage:
    from agent_compiler.migrations import run_migrations
    await run_migrations(engine)
"""

import asyncio
from datetime import datetime, timezone
from typing import Callable, Awaitable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


# Migration type: (version, name, migration_function)
Migration = tuple[int, str, Callable[[AsyncEngine], Awaitable[None]]]


async def _create_schema_version_table(engine: AsyncEngine) -> None:
    """Create the schema_version table if it doesn't exist."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """))


async def _get_current_version(engine: AsyncEngine) -> int:
    """Get the current schema version."""
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT MAX(version) FROM schema_version"
        ))
        row = result.fetchone()
        return row[0] if row and row[0] is not None else 0


async def _record_migration(engine: AsyncEngine, version: int, name: str) -> None:
    """Record a migration as applied."""
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO schema_version (version, name, applied_at)
                VALUES (:version, :name, :applied_at)
            """),
            {
                "version": version,
                "name": name,
                "applied_at": datetime.now(timezone.utc).isoformat(),
            }
        )


# =============================================================================
# Migrations
# =============================================================================

async def migration_001_initial_schema(engine: AsyncEngine) -> None:
    """Initial schema - tables created by SQLModel.

    This migration is a no-op since SQLModel creates tables automatically.
    It exists to establish the migration baseline.
    """
    # Tables are created by SQLModel.metadata.create_all()
    # This migration just marks the initial state
    logger.info("Migration 001: Initial schema (baseline)")


async def migration_002_add_export_target(engine: AsyncEngine) -> None:
    """Add target column to exports table."""
    async with engine.begin() as conn:
        # Check if column exists (SQLite specific)
        result = await conn.execute(text(
            "PRAGMA table_info(exports)"
        ))
        columns = {row[1] for row in result.fetchall()}

        if "target" not in columns:
            await conn.execute(text("""
                ALTER TABLE exports ADD COLUMN target TEXT DEFAULT 'langgraph'
            """))
            logger.info("Migration 002: Added 'target' column to exports")
        else:
            logger.info("Migration 002: 'target' column already exists")


async def migration_003_add_step_artifacts(engine: AsyncEngine) -> None:
    """Add step_artifacts table for deterministic replay."""
    async with engine.begin() as conn:
        # Check if table exists
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='step_artifacts'"
        ))
        if result.fetchone():
            logger.info("Migration 003: 'step_artifacts' table already exists")
            return

        await conn.execute(text("""
            CREATE TABLE step_artifacts (
                id TEXT PRIMARY KEY,
                step_id TEXT NOT NULL REFERENCES steps(id),
                artifact_type TEXT NOT NULL,
                artifact_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX ix_step_artifacts_step_id ON step_artifacts(step_id)"
        ))
        logger.info("Migration 003: Created 'step_artifacts' table")


async def migration_004_add_eval_tables(engine: AsyncEngine) -> None:
    """Add tables for eval suites and results."""
    async with engine.begin() as conn:
        # Check if eval_suites table exists
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='eval_suites'"
        ))
        if result.fetchone():
            logger.info("Migration 004: Eval tables already exist")
            return

        # Create eval_suites table
        await conn.execute(text("""
            CREATE TABLE eval_suites (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                flow_id TEXT NOT NULL REFERENCES flows(id),
                config_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX ix_eval_suites_flow_id ON eval_suites(flow_id)"
        ))

        # Create eval_cases table
        await conn.execute(text("""
            CREATE TABLE eval_cases (
                id TEXT PRIMARY KEY,
                suite_id TEXT NOT NULL REFERENCES eval_suites(id),
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                input_json TEXT NOT NULL,
                expected_json TEXT DEFAULT '{}',
                assertions_json TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX ix_eval_cases_suite_id ON eval_cases(suite_id)"
        ))

        # Create eval_runs table
        await conn.execute(text("""
            CREATE TABLE eval_runs (
                id TEXT PRIMARY KEY,
                suite_id TEXT NOT NULL REFERENCES eval_suites(id),
                status TEXT NOT NULL,
                total_cases INTEGER DEFAULT 0,
                passed_cases INTEGER DEFAULT 0,
                failed_cases INTEGER DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX ix_eval_runs_suite_id ON eval_runs(suite_id)"
        ))

        # Create eval_case_results table
        await conn.execute(text("""
            CREATE TABLE eval_case_results (
                id TEXT PRIMARY KEY,
                eval_run_id TEXT NOT NULL REFERENCES eval_runs(id),
                case_id TEXT NOT NULL REFERENCES eval_cases(id),
                run_id TEXT REFERENCES runs(id),
                status TEXT NOT NULL,
                assertions_json TEXT DEFAULT '[]',
                error_message TEXT,
                duration_ms REAL,
                created_at TEXT NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX ix_eval_case_results_eval_run_id ON eval_case_results(eval_run_id)"
        ))

        logger.info("Migration 004: Created eval tables")


async def migration_005_add_template_fields(engine: AsyncEngine) -> None:
    """Add template_id and template_version columns to flows table."""
    async with engine.begin() as conn:
        # Check if columns exist (SQLite specific)
        result = await conn.execute(text(
            "PRAGMA table_info(flows)"
        ))
        columns = {row[1] for row in result.fetchall()}

        if "template_id" not in columns:
            await conn.execute(text("""
                ALTER TABLE flows ADD COLUMN template_id TEXT DEFAULT NULL
            """))
            logger.info("Migration 005: Added 'template_id' column to flows")

        if "template_version" not in columns:
            await conn.execute(text("""
                ALTER TABLE flows ADD COLUMN template_version TEXT DEFAULT NULL
            """))
            logger.info("Migration 005: Added 'template_version' column to flows")

        if "template_id" in columns and "template_version" in columns:
            logger.info("Migration 005: Template columns already exist")


async def migration_006_add_credentials_table(engine: AsyncEngine) -> None:
    """Add credentials table for encrypted provider API keys."""
    async with engine.begin() as conn:
        # Check if table exists
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='credentials'"
        ))
        if result.fetchone():
            logger.info("Migration 006: 'credentials' table already exists")
            return

        await conn.execute(text("""
            CREATE TABLE credentials (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                name TEXT,
                secret_ciphertext TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_tested_at TEXT,
                last_test_status TEXT,
                last_test_error TEXT
            )
        """))
        # Create indexes for efficient lookup
        await conn.execute(text(
            "CREATE INDEX ix_credentials_provider ON credentials(provider)"
        ))
        await conn.execute(text(
            "CREATE INDEX ix_credentials_scope_type ON credentials(scope_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX ix_credentials_scope_id ON credentials(scope_id)"
        ))
        # Composite index for resolution queries
        await conn.execute(text(
            "CREATE INDEX ix_credentials_resolution ON credentials(provider, scope_type, scope_id)"
        ))
        logger.info("Migration 006: Created 'credentials' table with indexes")


async def migration_007_add_run_meta_json(engine: AsyncEngine) -> None:
    """Add meta_json column to runs table for replay metadata."""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(runs)"))
        columns = {row[1] for row in result.fetchall()}

        if "meta_json" not in columns:
            await conn.execute(text("""
                ALTER TABLE runs ADD COLUMN meta_json TEXT DEFAULT '{}'
            """))
            logger.info("Migration 007: Added 'meta_json' column to runs")
        else:
            logger.info("Migration 007: 'meta_json' column already exists")


async def migration_008_add_step_token_columns(engine: AsyncEngine) -> None:
    """Add token tracking columns to steps table."""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(steps)"))
        columns = {row[1] for row in result.fetchall()}

        for col, typedef in [
            ("tokens_input", "INTEGER"),
            ("tokens_output", "INTEGER"),
            ("tokens_total", "INTEGER"),
            ("model_name", "TEXT"),
        ]:
            if col not in columns:
                await conn.execute(text(f"ALTER TABLE steps ADD COLUMN {col} {typedef}"))
                logger.info(f"Migration 008: Added '{col}' to steps")
            else:
                logger.info(f"Migration 008: '{col}' already exists in steps")


async def migration_009_add_flow_versions_table(engine: AsyncEngine) -> None:
    """Create flow_versions table for version history."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flow_versions (
                id TEXT PRIMARY KEY,
                flow_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                ir_json TEXT NOT NULL,
                label TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (flow_id) REFERENCES flows(id)
            )
        """))
        # Index for quick version lookups
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_flow_versions_flow_id
            ON flow_versions(flow_id, version_number DESC)
        """))
        logger.info("Migration 009: Created flow_versions table")


async def migration_010_add_flow_env_vars_table(engine: AsyncEngine) -> None:
    """Create flow_env_vars table for per-flow, per-profile environment variables."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flow_env_vars (
                id TEXT PRIMARY KEY,
                flow_id TEXT NOT NULL,
                profile TEXT NOT NULL DEFAULT 'development',
                key TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                is_secret INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (flow_id) REFERENCES flows(id),
                UNIQUE(flow_id, profile, key)
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_flow_env_vars_flow_profile
            ON flow_env_vars(flow_id, profile)
        """))
        logger.info("Migration 010: Created flow_env_vars table")


async def migration_011_add_model_cache_table(engine: AsyncEngine) -> None:
    """Add model_cache table for persistent LLM model list caching."""
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='model_cache'"
        ))
        if result.fetchone():
            logger.info("Migration 011: 'model_cache' table already exists")
            return

        await conn.execute(text("""
            CREATE TABLE model_cache (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                credential_fingerprint TEXT NOT NULL,
                region TEXT,
                payload_json TEXT NOT NULL DEFAULT '[]',
                etag TEXT NOT NULL DEFAULT '',
                fetched_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE UNIQUE INDEX uq_model_cache_key
            ON model_cache(project_id, provider, credential_fingerprint, region)
        """))
        await conn.execute(text(
            "CREATE INDEX ix_model_cache_expires ON model_cache(expires_at)"
        ))
        logger.info("Migration 011: Created 'model_cache' table with indexes")


async def migration_012_add_gitops_jobs_table(engine: AsyncEngine) -> None:
    """Add gitops_jobs table for tracking async PR creation jobs."""
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='gitops_jobs'"
        ))
        if result.fetchone():
            logger.info("Migration 012: 'gitops_jobs' table already exists")
            return

        await conn.execute(text("""
            CREATE TABLE gitops_jobs (
                id TEXT PRIMARY KEY,
                export_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                repo TEXT NOT NULL,
                base_branch TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                pr_title TEXT,
                pr_body TEXT,
                pr_url TEXT,
                pr_number INTEGER,
                commit_sha TEXT,
                files_total INTEGER DEFAULT 0,
                files_uploaded INTEGER DEFAULT 0,
                logs_json TEXT DEFAULT '[]',
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX ix_gitops_jobs_export_id ON gitops_jobs(export_id)"
        ))
        logger.info("Migration 012: Created 'gitops_jobs' table")


async def migration_013_encrypt_existing_env_var_secrets(engine: AsyncEngine) -> None:
    """Encrypt existing plaintext FlowEnvVar secrets in-place.

    Idempotent: skips values that are already encrypted (detected by
    attempting decryption first). If encryption is not configured,
    logs a warning and skips.
    """
    from agent_compiler.services.encryption_service import (
        encrypt_secret,
        decrypt_secret,
        is_encryption_configured,
        EncryptionError,
        MasterKeyNotConfiguredError,
    )

    if not is_encryption_configured():
        logger.warning(
            "Migration 013: FORGE_MASTER_KEY not set — skipping encryption of "
            "existing env var secrets. Set the key and re-run migrations to encrypt."
        )
        return

    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT id, value FROM flow_env_vars WHERE is_secret = 1"
        ))
        rows = result.fetchall()

        encrypted_count = 0
        skipped_count = 0
        for row_id, value in rows:
            if not value:
                continue
            # Check if already encrypted by attempting decryption
            try:
                decrypt_secret(value)
                # Decryption succeeded → already encrypted
                skipped_count += 1
                continue
            except (EncryptionError, MasterKeyNotConfiguredError):
                # Decryption failed → plaintext, needs encryption
                pass

            ciphertext = encrypt_secret(value)
            await conn.execute(
                text("UPDATE flow_env_vars SET value = :value WHERE id = :id"),
                {"value": ciphertext, "id": row_id},
            )
            encrypted_count += 1

        logger.info(
            f"Migration 013: Encrypted {encrypted_count} env var secrets "
            f"(skipped {skipped_count} already-encrypted)"
        )


async def migration_014_add_multiagent_tables(engine: AsyncEngine) -> None:
    """Add multi-agent support: agent fields on steps/runs + agent_events table."""
    async with engine.begin() as conn:
        # ── steps: add agent_id, parent_step_id, depth ──
        result = await conn.execute(text("PRAGMA table_info(steps)"))
        columns = {row[1] for row in result.fetchall()}

        for col, typedef, default in [
            ("agent_id", "TEXT", None),
            ("parent_step_id", "TEXT", None),
            ("depth", "INTEGER", "0"),
        ]:
            if col not in columns:
                default_clause = f" DEFAULT {default}" if default is not None else ""
                await conn.execute(
                    text(f"ALTER TABLE steps ADD COLUMN {col} {typedef}{default_clause}")
                )
                logger.info(f"Migration 014: Added '{col}' to steps")

        # ── runs: add entrypoint ──
        result = await conn.execute(text("PRAGMA table_info(runs)"))
        columns = {row[1] for row in result.fetchall()}

        if "entrypoint" not in columns:
            await conn.execute(
                text("ALTER TABLE runs ADD COLUMN entrypoint TEXT DEFAULT 'main'")
            )
            logger.info("Migration 014: Added 'entrypoint' to runs")

        # ── agent_events table ──
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_events'"
        ))
        if not result.fetchone():
            await conn.execute(text("""
                CREATE TABLE agent_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    event_type TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    parent_agent_id TEXT,
                    data_json TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL,
                    depth INTEGER DEFAULT 0
                )
            """))
            await conn.execute(text(
                "CREATE INDEX ix_agent_events_run_id ON agent_events(run_id)"
            ))
            logger.info("Migration 014: Created 'agent_events' table")
        else:
            logger.info("Migration 014: 'agent_events' table already exists")


async def migration_015_add_v21_runtime_markers(engine: AsyncEngine) -> None:
    """Record schema milestone for v2.1 runtime features.

    Timeline event variants are stored as plain text values in SQLite,
    so no ALTER TABLE is required.
    """
    _ = engine
    logger.info("Migration 015: v2.1 runtime markers (no-op)")


async def migration_016_add_run_events_table(engine: AsyncEngine) -> None:
    """Add run_events table for fine-grained debug timeline (PR2)."""
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_events'"
        ))
        if result.fetchone():
            logger.info("Migration 016: 'run_events' table already exists")
            return

        await conn.execute(text("""
            CREATE TABLE run_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                ts TEXT NOT NULL,
                seq INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                hash TEXT
            )
        """))
        await conn.execute(text(
            "CREATE INDEX ix_run_events_run_id ON run_events(run_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX ix_run_events_run_seq ON run_events(run_id, seq)"
        ))
        logger.info("Migration 016: Created 'run_events' table")


async def migration_017_add_eval_run_gate_report(engine: AsyncEngine) -> None:
    """Add gate_passed and report_json columns to eval_runs (PR3)."""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(eval_runs)"))
        columns = {row[1] for row in result.fetchall()}

        if "gate_passed" not in columns:
            await conn.execute(text(
                "ALTER TABLE eval_runs ADD COLUMN gate_passed INTEGER"
            ))
            logger.info("Migration 017: Added 'gate_passed' column to eval_runs")

        if "report_json" not in columns:
            await conn.execute(text(
                "ALTER TABLE eval_runs ADD COLUMN report_json TEXT"
            ))
            logger.info("Migration 017: Added 'report_json' column to eval_runs")


# List of all migrations in order
MIGRATIONS: list[Migration] = [
    (1, "initial_schema", migration_001_initial_schema),
    (2, "add_export_target", migration_002_add_export_target),
    (3, "add_step_artifacts", migration_003_add_step_artifacts),
    (4, "add_eval_tables", migration_004_add_eval_tables),
    (5, "add_template_fields", migration_005_add_template_fields),
    (6, "add_credentials_table", migration_006_add_credentials_table),
    (7, "add_run_meta_json", migration_007_add_run_meta_json),
    (8, "add_step_token_columns", migration_008_add_step_token_columns),
    (9, "add_flow_versions_table", migration_009_add_flow_versions_table),
    (10, "add_flow_env_vars_table", migration_010_add_flow_env_vars_table),
    (11, "add_model_cache_table", migration_011_add_model_cache_table),
    (12, "add_gitops_jobs_table", migration_012_add_gitops_jobs_table),
    (13, "encrypt_existing_env_var_secrets", migration_013_encrypt_existing_env_var_secrets),
    (14, "add_multiagent_tables", migration_014_add_multiagent_tables),
    (15, "add_v21_runtime_markers", migration_015_add_v21_runtime_markers),
    (16, "add_run_events_table", migration_016_add_run_events_table),
    (17, "add_eval_run_gate_report", migration_017_add_eval_run_gate_report),
]


async def run_migrations(engine: AsyncEngine) -> int:
    """Run pending migrations.

    Args:
        engine: SQLAlchemy async engine

    Returns:
        Number of migrations applied
    """
    # Ensure schema_version table exists
    await _create_schema_version_table(engine)

    # Get current version
    current_version = await _get_current_version(engine)
    logger.info(f"Current schema version: {current_version}")

    # Apply pending migrations
    applied = 0
    for version, name, migration_fn in MIGRATIONS:
        if version > current_version:
            logger.info(f"Applying migration {version}: {name}")
            try:
                await migration_fn(engine)
                await _record_migration(engine, version, name)
                applied += 1
            except Exception as e:
                logger.error(f"Migration {version} failed: {e}")
                raise

    if applied:
        logger.info(f"Applied {applied} migrations")
    else:
        logger.info("No migrations to apply")

    return applied


async def get_migration_status(engine: AsyncEngine) -> dict:
    """Get current migration status.

    Returns:
        Dictionary with migration info
    """
    await _create_schema_version_table(engine)
    current_version = await _get_current_version(engine)

    # Get applied migrations
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT version, name, applied_at FROM schema_version ORDER BY version"
        ))
        applied = [
            {"version": row[0], "name": row[1], "applied_at": row[2]}
            for row in result.fetchall()
        ]

    # Get pending migrations
    pending = [
        {"version": v, "name": n}
        for v, n, _ in MIGRATIONS
        if v > current_version
    ]

    return {
        "current_version": current_version,
        "latest_version": MIGRATIONS[-1][0] if MIGRATIONS else 0,
        "applied": applied,
        "pending": pending,
    }
