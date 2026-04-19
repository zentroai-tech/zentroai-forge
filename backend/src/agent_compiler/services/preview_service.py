"""Preview service for code preview API.

Handles manifest generation, file serving, and security sanitization.
"""

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import ExportRecord, ExportStatus
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

MAX_FILE_BYTES = 200_000  # 200 KB
MAX_TOTAL_FILES = 5000

# Extension to language mapping
LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".md": "markdown",
    ".toml": "toml",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".txt": "text",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".css": "css",
    ".html": "html",
    ".htm": "html",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".xml": "xml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".env.example": "shell",
    ".gitignore": "text",
    ".dockerignore": "text",
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
}

# Forbidden file patterns (exact names or globs)
FORBIDDEN_FILES: set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "id_rsa",
    "id_rsa.pub",
    "id_ed25519",
    "id_ed25519.pub",
    "known_hosts",
}

# Forbidden file extensions
FORBIDDEN_EXTENSIONS: set[str] = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".der",
}

# Forbidden directory names
FORBIDDEN_DIRS: set[str] = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "egg-info",
    ".eggs",
}

# Regex for forbidden filenames
FORBIDDEN_FILENAME_PATTERN = re.compile(
    r"(token|secret|password|apikey|api_key|private_key|credentials)",
    re.IGNORECASE,
)

# Binary file extensions (non-text)
BINARY_EXTENSIONS: set[str] = {
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".lib",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".webp",
    ".bmp",
    ".tiff",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
}

# Patterns for content redaction
REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API keys in various formats
    (re.compile(r'(OPENAI_API_KEY\s*[=:]\s*)["\']?[^"\'\s]+["\']?', re.IGNORECASE), r'\1"***REDACTED***"'),
    (re.compile(r'(ANTHROPIC_API_KEY\s*[=:]\s*)["\']?[^"\'\s]+["\']?', re.IGNORECASE), r'\1"***REDACTED***"'),
    (re.compile(r'(API_KEY\s*[=:]\s*)["\']?[^"\'\s]+["\']?', re.IGNORECASE), r'\1"***REDACTED***"'),
    (re.compile(r'(SECRET_KEY\s*[=:]\s*)["\']?[^"\'\s]+["\']?', re.IGNORECASE), r'\1"***REDACTED***"'),
    (re.compile(r'(PASSWORD\s*[=:]\s*)["\']?[^"\'\s]+["\']?', re.IGNORECASE), r'\1"***REDACTED***"'),
    (re.compile(r'(DATABASE_URL\s*[=:]\s*)["\']?[^"\'\s]+["\']?', re.IGNORECASE), r'\1"***REDACTED***"'),
    # Bearer tokens
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-_]+\.?[A-Za-z0-9\-_]*\.?[A-Za-z0-9\-_]*'), r'\1***REDACTED***'),
    # sk- prefixed keys (OpenAI format, may contain hyphens)
    (re.compile(r'sk-[A-Za-z0-9\-_]{20,}'), '***REDACTED***'),
]


# =============================================================================
# Security Functions
# =============================================================================

def is_path_safe(base_path: Path, requested_path: str) -> bool:
    """Check if a requested path is safely within the base path.

    Prevents path traversal attacks.
    """
    try:
        # Resolve both paths to absolute
        base = base_path.resolve()
        full_path = (base / requested_path).resolve()

        # Check that the resolved path is within base
        return str(full_path).startswith(str(base) + os.sep) or full_path == base
    except (ValueError, OSError):
        return False


def is_file_forbidden(file_path: Path) -> bool:
    """Check if a file should be excluded from preview."""
    name = file_path.name
    suffix = file_path.suffix.lower()

    # Check exact name matches
    if name in FORBIDDEN_FILES:
        return True

    # Check .env.* pattern
    if name.startswith(".env"):
        return True

    # Check forbidden extensions
    if suffix in FORBIDDEN_EXTENSIONS:
        return True

    # Check filename pattern (contains sensitive words)
    if FORBIDDEN_FILENAME_PATTERN.search(name):
        return True

    return False


def is_dir_forbidden(dir_name: str) -> bool:
    """Check if a directory should be excluded."""
    # Handle .egg-info directories
    if dir_name.endswith(".egg-info"):
        return True
    return dir_name in FORBIDDEN_DIRS


def is_binary_file(file_path: Path) -> bool:
    """Check if a file is binary based on extension."""
    return file_path.suffix.lower() in BINARY_EXTENSIONS


def get_language(file_path: Path) -> str:
    """Get the language/syntax type for a file."""
    name = file_path.name
    suffix = file_path.suffix.lower()

    # Check exact filename matches first
    if name in LANGUAGE_MAP:
        return LANGUAGE_MAP[name]

    # Check extension
    return LANGUAGE_MAP.get(suffix, "text")


def redact_content(content: str) -> str:
    """Redact sensitive information from file content."""
    result = content
    for pattern, replacement in REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def compute_sha256(content: bytes) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file efficiently."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# =============================================================================
# Manifest Generation
# =============================================================================

def generate_manifest(
    export_id: str,
    export_dir: Path,
    ir_version: str = "2",
    created_at: datetime | None = None,
    target: str = "langgraph",
    flow_id: str | None = None,
    flow_name: str | None = None,
) -> dict[str, Any]:
    """Generate a manifest for an export directory.

    Args:
        export_id: The export ID
        export_dir: Path to the export directory
        ir_version: IR version string
        created_at: Creation timestamp

    Returns:
        Manifest dictionary
    """
    files: list[dict[str, Any]] = []
    truncated = False

    # Walk the directory and collect files
    all_files: list[Path] = []

    for root, dirs, filenames in os.walk(export_dir):
        root_path = Path(root)

        # Filter out forbidden directories (modify in-place to skip recursion)
        dirs[:] = [d for d in dirs if not is_dir_forbidden(d)]

        for filename in filenames:
            file_path = root_path / filename

            # Skip forbidden files
            if is_file_forbidden(file_path):
                continue

            # Skip binary files
            if is_binary_file(file_path):
                continue

            all_files.append(file_path)

    # Sort by relative path for deterministic ordering
    all_files.sort(key=lambda p: str(p.relative_to(export_dir)))

    # Check if we need to truncate
    if len(all_files) > MAX_TOTAL_FILES:
        truncated = True
        all_files = all_files[:MAX_TOTAL_FILES]

    # Build file entries
    for file_path in all_files:
        try:
            stat = file_path.stat()
            rel_path = str(file_path.relative_to(export_dir)).replace("\\", "/")

            files.append({
                "path": rel_path,
                "size": stat.st_size,
                "language": get_language(file_path),
                "sha256": compute_file_sha256(file_path),
            })
        except OSError as e:
            logger.warning(f"Failed to stat file {file_path}: {e}")
            continue

    # Determine entrypoints based on target
    if target == "langgraph":
        # LangGraph exports have graph.py and main.py as entrypoints
        entrypoints = [
            f["path"] for f in files
            if f["path"].endswith("graph.py") or f["path"].endswith("main.py")
        ]
    else:
        # Runtime exports have main.py as entrypoint
        entrypoints = [
            f["path"] for f in files
            if f["path"].endswith("main.py") or f["path"].endswith("__main__.py")
        ]

    return {
        "export_id": export_id,
        "flow_id": flow_id,
        "flow_name": flow_name,
        "target": target,
        "root": export_dir.name,
        "ir_version": ir_version,
        "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
        "total_files": len(files),
        "files": files,
        "entrypoints": entrypoints,
        "truncated": truncated,
        "limits": {
            "max_file_bytes": MAX_FILE_BYTES,
            "max_total_files": MAX_TOTAL_FILES,
        },
    }


def compute_manifest_etag(manifest: dict[str, Any]) -> str:
    """Compute an ETag for a manifest based on file hashes."""
    # Combine all file hashes
    combined = "".join(f["sha256"] for f in manifest.get("files", []))
    return hashlib.md5(combined.encode()).hexdigest()


# =============================================================================
# Preview Service
# =============================================================================

class PreviewService:
    """Service for handling code preview operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_export(self, export_id: str) -> ExportRecord | None:
        """Get an export by ID."""
        statement = select(ExportRecord).where(ExportRecord.id == export_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create_export(
        self,
        flow_id: str,
        export_dir: Path,
        zip_path: Path,
        target: str = "langgraph",
    ) -> ExportRecord:
        """Create a new export record."""
        export_id = str(uuid.uuid4())

        export = ExportRecord(
            id=export_id,
            flow_id=flow_id,
            status=ExportStatus.READY,
            target=target,
            export_dir_path=str(export_dir),
            zip_path=str(zip_path),
        )

        self.session.add(export)
        await self.session.commit()
        await self.session.refresh(export)

        logger.info(f"Created export: {export_id} for flow: {flow_id}")
        return export

    async def get_or_generate_manifest(
        self,
        export: ExportRecord,
        flow_name: str | None = None,
    ) -> dict[str, Any]:
        """Get cached manifest or generate a new one."""
        export_dir = Path(export.export_dir_path)

        if not export_dir.exists():
            raise FileNotFoundError(f"Export directory not found: {export_dir}")

        # Check if we have a cached manifest
        if export.manifest_json:
            manifest = export.manifest_data
            current_etag = compute_manifest_etag(manifest)

            # Verify cache is still valid
            if current_etag == export.manifest_etag:
                return manifest

        # Generate new manifest
        manifest = generate_manifest(
            export_id=export.id,
            export_dir=export_dir,
            created_at=export.created_at,
            target=export.target or "langgraph",
            flow_id=export.flow_id,
            flow_name=flow_name,
        )

        # Cache the manifest
        export.manifest_data = manifest
        export.manifest_etag = compute_manifest_etag(manifest)

        self.session.add(export)
        await self.session.commit()

        return manifest

    async def get_file_content(
        self,
        export: ExportRecord,
        file_path: str,
        manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get content of a single file with security checks.

        Args:
            export: The export record
            file_path: Relative path to the file
            manifest: Optional pre-loaded manifest for validation

        Returns:
            File content response dict

        Raises:
            FileNotFoundError: If file not found
            PermissionError: If file is forbidden
            ValueError: If file is binary
        """
        export_dir = Path(export.export_dir_path)

        # Security: Validate path is within export directory
        if not is_path_safe(export_dir, file_path):
            raise PermissionError(f"Path traversal attempt detected: {file_path}")

        full_path = export_dir / file_path

        # Check file exists
        if not full_path.exists() or not full_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Security: Check if file is forbidden
        if is_file_forbidden(full_path):
            raise PermissionError(f"Access to this file is forbidden: {file_path}")

        # Check if file is binary
        if is_binary_file(full_path):
            raise ValueError(f"Binary files are not supported: {file_path}")

        # Validate against manifest if provided
        if manifest:
            manifest_paths = {f["path"] for f in manifest.get("files", [])}
            normalized_path = file_path.replace("\\", "/")
            if normalized_path not in manifest_paths:
                raise FileNotFoundError(f"File not in manifest: {file_path}")

        # Read file content
        file_size = full_path.stat().st_size
        truncated = False

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                if file_size > MAX_FILE_BYTES:
                    content = f.read(MAX_FILE_BYTES)
                    truncated = True
                else:
                    content = f.read()
        except UnicodeDecodeError:
            raise ValueError(f"File is not valid UTF-8 text: {file_path}")

        # Redact sensitive content
        content = redact_content(content)

        # Compute hash of original file
        file_hash = compute_file_sha256(full_path)

        return {
            "path": file_path.replace("\\", "/"),
            "content": content,
            "encoding": "utf-8",
            "language": get_language(full_path),
            "truncated": truncated,
            "size": file_size,
            "sha256": file_hash,
        }

    async def list_exports_for_flow(
        self,
        flow_id: str,
        limit: int = 10,
    ) -> list[ExportRecord]:
        """List recent exports for a flow."""
        statement = (
            select(ExportRecord)
            .where(ExportRecord.flow_id == flow_id)
            .order_by(ExportRecord.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
