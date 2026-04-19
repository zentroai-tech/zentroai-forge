"""Export cleanup service for removing expired exports."""

import asyncio
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.config import get_settings
from agent_compiler.database import get_session_context
from agent_compiler.models.db import ExportRecord, ExportStatus
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class CleanupService:
    """Service for cleaning up expired exports."""

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
        self._settings = get_settings()

    async def cleanup_expired_exports(self) -> dict[str, int]:
        """Clean up exports older than TTL.

        Returns:
            Dictionary with cleanup statistics
        """
        ttl_hours = self._settings.export_ttl_hours
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        export_base_dir = self._settings.export_temp_dir

        stats = {
            "exports_checked": 0,
            "exports_cleaned": 0,
            "files_deleted": 0,
            "errors": 0,
        }

        logger.info(f"Starting export cleanup (TTL: {ttl_hours} hours)")

        # Get all exports older than TTL
        statement = (
            select(ExportRecord)
            .where(ExportRecord.created_at < cutoff_time)
            .where(ExportRecord.status != ExportStatus.EXPIRED)
        )

        if self.session:
            result = await self.session.execute(statement)
            exports = list(result.scalars().all())
        else:
            async with get_session_context() as session:
                result = await session.execute(statement)
                exports = list(result.scalars().all())

        stats["exports_checked"] = len(exports)

        for export in exports:
            try:
                cleaned = await self._cleanup_single_export(export, export_base_dir)
                if cleaned:
                    stats["exports_cleaned"] += 1
                    stats["files_deleted"] += cleaned
            except Exception as e:
                logger.error(f"Error cleaning export {export.id}: {e}")
                stats["errors"] += 1

        logger.info(
            f"Cleanup complete: {stats['exports_cleaned']} exports cleaned, "
            f"{stats['files_deleted']} files deleted, {stats['errors']} errors"
        )

        return stats

    async def _cleanup_single_export(
        self,
        export: ExportRecord,
        export_base_dir: Path,
    ) -> int:
        """Clean up a single export.

        Args:
            export: The export record to clean
            export_base_dir: Base directory for exports

        Returns:
            Number of files deleted
        """
        files_deleted = 0

        # Validate paths are within export directory (security)
        export_dir = Path(export.export_dir_path) if export.export_dir_path else None
        zip_path = Path(export.zip_path) if export.zip_path else None

        # Delete export directory
        if export_dir and export_dir.exists():
            if self._is_safe_path(export_dir, export_base_dir):
                try:
                    file_count = sum(1 for _ in export_dir.rglob("*") if _.is_file())
                    shutil.rmtree(export_dir)
                    files_deleted += file_count
                    logger.debug(f"Deleted export directory: {export_dir}")
                except Exception as e:
                    logger.error(f"Failed to delete directory {export_dir}: {e}")
            else:
                logger.warning(f"Skipping unsafe path: {export_dir}")

        # Delete zip file
        if zip_path and zip_path.exists():
            if self._is_safe_path(zip_path, export_base_dir):
                try:
                    zip_path.unlink()
                    files_deleted += 1
                    logger.debug(f"Deleted zip file: {zip_path}")
                except Exception as e:
                    logger.error(f"Failed to delete zip {zip_path}: {e}")
            else:
                logger.warning(f"Skipping unsafe zip path: {zip_path}")

        # Mark export as expired
        export.status = ExportStatus.EXPIRED

        if self.session:
            self.session.add(export)
            await self.session.commit()
        else:
            async with get_session_context() as session:
                session.add(export)
                await session.commit()

        logger.info(f"Cleaned export {export.id} ({files_deleted} files)")
        return files_deleted

    def _is_safe_path(self, path: Path, base_dir: Path) -> bool:
        """Check if path is safely within the base directory.

        Prevents path traversal attacks.
        """
        try:
            resolved_path = path.resolve()
            resolved_base = base_dir.resolve()

            # Check that path starts with base directory
            return str(resolved_path).startswith(str(resolved_base))
        except (ValueError, OSError):
            return False


# Background task for periodic cleanup
_cleanup_task: Optional[asyncio.Task] = None


async def _cleanup_loop(interval_hours: float = 1.0):
    """Background loop for periodic cleanup."""
    logger.info(f"Starting cleanup background task (interval: {interval_hours}h)")

    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            service = CleanupService()
            await service.cleanup_expired_exports()
        except asyncio.CancelledError:
            logger.info("Cleanup background task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in cleanup loop: {e}")
            # Continue running even after errors
            await asyncio.sleep(60)  # Wait a minute before retrying


def start_cleanup_task(interval_hours: float = 1.0) -> asyncio.Task:
    """Start the background cleanup task.

    Args:
        interval_hours: How often to run cleanup (default: 1 hour)

    Returns:
        The cleanup task
    """
    global _cleanup_task

    if _cleanup_task is not None and not _cleanup_task.done():
        logger.warning("Cleanup task already running")
        return _cleanup_task

    _cleanup_task = asyncio.create_task(_cleanup_loop(interval_hours))
    return _cleanup_task


def stop_cleanup_task():
    """Stop the background cleanup task."""
    global _cleanup_task

    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
        logger.info("Cleanup task stopped")
