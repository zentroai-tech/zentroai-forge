"""Tests for preview service and code preview API."""

import tempfile
from pathlib import Path

import pytest

from agent_compiler.services.preview_service import (
    MAX_FILE_BYTES,
    compute_file_sha256,
    compute_sha256,
    generate_manifest,
    get_language,
    is_binary_file,
    is_dir_forbidden,
    is_file_forbidden,
    is_path_safe,
    redact_content,
)


class TestPathSafety:
    """Tests for path traversal prevention."""

    def test_safe_path_simple(self):
        """Test simple safe path."""
        base = Path("/tmp/exports/abc123")
        assert is_path_safe(base, "src/main.py") is True

    def test_safe_path_nested(self):
        """Test nested safe path."""
        base = Path("/tmp/exports/abc123")
        assert is_path_safe(base, "src/agent_app/adapters/langchain.py") is True

    def test_unsafe_path_traversal_dotdot(self):
        """Test path traversal with .."""
        base = Path("/tmp/exports/abc123")
        assert is_path_safe(base, "../../../etc/passwd") is False

    def test_unsafe_path_traversal_encoded(self):
        """Test path traversal attempt."""
        base = Path("/tmp/exports/abc123")
        assert is_path_safe(base, "src/../../etc/passwd") is False

    def test_unsafe_absolute_path(self):
        """Test absolute path rejection."""
        base = Path("/tmp/exports/abc123")
        # Absolute paths should resolve outside base
        assert is_path_safe(base, "/etc/passwd") is False

    def test_safe_path_with_dots_in_filename(self):
        """Test safe path with dots in filename."""
        base = Path("/tmp/exports/abc123")
        assert is_path_safe(base, "src/file.test.py") is True

    def test_empty_path(self):
        """Test empty path resolves to base."""
        base = Path("/tmp/exports/abc123")
        assert is_path_safe(base, "") is True


class TestForbiddenFiles:
    """Tests for file filtering."""

    def test_env_file_forbidden(self):
        """Test .env files are forbidden."""
        assert is_file_forbidden(Path(".env")) is True
        assert is_file_forbidden(Path(".env.local")) is True
        assert is_file_forbidden(Path(".env.production")) is True
        assert is_file_forbidden(Path("src/.env")) is True

    def test_key_files_forbidden(self):
        """Test key/cert files are forbidden."""
        assert is_file_forbidden(Path("server.key")) is True
        assert is_file_forbidden(Path("cert.pem")) is True
        assert is_file_forbidden(Path("keystore.p12")) is True

    def test_sensitive_names_forbidden(self):
        """Test files with sensitive words in name are forbidden."""
        assert is_file_forbidden(Path("api_key.txt")) is True
        assert is_file_forbidden(Path("secrets.json")) is True
        assert is_file_forbidden(Path("password_store.txt")) is True
        assert is_file_forbidden(Path("TOKEN_FILE")) is True

    def test_ssh_keys_forbidden(self):
        """Test SSH keys are forbidden."""
        assert is_file_forbidden(Path("id_rsa")) is True
        assert is_file_forbidden(Path("id_rsa.pub")) is True
        assert is_file_forbidden(Path("id_ed25519")) is True

    def test_normal_files_allowed(self):
        """Test normal code files are allowed."""
        assert is_file_forbidden(Path("main.py")) is False
        assert is_file_forbidden(Path("README.md")) is False
        assert is_file_forbidden(Path("pyproject.toml")) is False
        assert is_file_forbidden(Path("config.py")) is False


class TestForbiddenDirs:
    """Tests for directory filtering."""

    def test_git_forbidden(self):
        """Test .git directory is forbidden."""
        assert is_dir_forbidden(".git") is True

    def test_pycache_forbidden(self):
        """Test __pycache__ is forbidden."""
        assert is_dir_forbidden("__pycache__") is True

    def test_node_modules_forbidden(self):
        """Test node_modules is forbidden."""
        assert is_dir_forbidden("node_modules") is True

    def test_venv_forbidden(self):
        """Test virtual env dirs are forbidden."""
        assert is_dir_forbidden(".venv") is True
        assert is_dir_forbidden("venv") is True

    def test_egg_info_forbidden(self):
        """Test .egg-info directories are forbidden."""
        assert is_dir_forbidden("mypackage.egg-info") is True

    def test_normal_dirs_allowed(self):
        """Test normal directories are allowed."""
        assert is_dir_forbidden("src") is False
        assert is_dir_forbidden("tests") is False
        assert is_dir_forbidden("adapters") is False


class TestBinaryFiles:
    """Tests for binary file detection."""

    def test_compiled_files_binary(self):
        """Test compiled files are detected as binary."""
        assert is_binary_file(Path("module.pyc")) is True
        assert is_binary_file(Path("lib.so")) is True
        assert is_binary_file(Path("app.exe")) is True

    def test_images_binary(self):
        """Test image files are detected as binary."""
        assert is_binary_file(Path("logo.png")) is True
        assert is_binary_file(Path("photo.jpg")) is True
        assert is_binary_file(Path("icon.svg")) is True

    def test_archives_binary(self):
        """Test archive files are detected as binary."""
        assert is_binary_file(Path("data.zip")) is True
        assert is_binary_file(Path("backup.tar.gz")) is True

    def test_text_files_not_binary(self):
        """Test text files are not binary."""
        assert is_binary_file(Path("main.py")) is False
        assert is_binary_file(Path("README.md")) is False
        assert is_binary_file(Path("config.json")) is False


class TestLanguageDetection:
    """Tests for language detection."""

    def test_python_files(self):
        """Test Python file detection."""
        assert get_language(Path("main.py")) == "python"

    def test_markdown_files(self):
        """Test Markdown file detection."""
        assert get_language(Path("README.md")) == "markdown"

    def test_config_files(self):
        """Test config file detection."""
        assert get_language(Path("pyproject.toml")) == "toml"
        assert get_language(Path("config.json")) == "json"
        assert get_language(Path("settings.yaml")) == "yaml"

    def test_web_files(self):
        """Test web file detection."""
        assert get_language(Path("app.js")) == "javascript"
        assert get_language(Path("component.tsx")) == "typescript"
        assert get_language(Path("styles.css")) == "css"
        assert get_language(Path("index.html")) == "html"

    def test_unknown_extension(self):
        """Test unknown extension defaults to text."""
        assert get_language(Path("data.xyz")) == "text"


class TestContentRedaction:
    """Tests for content redaction."""

    def test_openai_key_redaction(self):
        """Test OpenAI API key redaction."""
        content = 'OPENAI_API_KEY="sk-abc123xyz789"'
        redacted = redact_content(content)
        assert "sk-abc123xyz789" not in redacted
        assert "REDACTED" in redacted

    def test_api_key_redaction(self):
        """Test generic API key redaction."""
        content = 'API_KEY = "my-secret-key"'
        redacted = redact_content(content)
        assert "my-secret-key" not in redacted
        assert "REDACTED" in redacted

    def test_password_redaction(self):
        """Test password redaction."""
        content = 'PASSWORD: supersecret123'
        redacted = redact_content(content)
        assert "supersecret123" not in redacted
        assert "REDACTED" in redacted

    def test_sk_prefix_redaction(self):
        """Test sk- prefixed keys are redacted."""
        content = 'key = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"'
        redacted = redact_content(content)
        assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in redacted

    def test_bearer_token_redaction(self):
        """Test Bearer token redaction."""
        content = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature'
        redacted = redact_content(content)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
        assert "REDACTED" in redacted

    def test_normal_content_unchanged(self):
        """Test normal content is not modified."""
        content = '''def main():
    print("Hello, World!")
    return 42
'''
        redacted = redact_content(content)
        assert redacted == content


class TestManifestGeneration:
    """Tests for manifest generation."""

    def test_manifest_structure(self):
        """Test manifest has required structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            (export_dir / "main.py").write_text("print('hello')")
            (export_dir / "README.md").write_text("# Project")

            manifest = generate_manifest("test-id", export_dir)

            assert manifest["export_id"] == "test-id"
            assert "files" in manifest
            assert "entrypoints" in manifest
            assert "truncated" in manifest
            assert "limits" in manifest
            assert manifest["limits"]["max_file_bytes"] == MAX_FILE_BYTES

    def test_manifest_excludes_forbidden(self):
        """Test manifest excludes forbidden files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            (export_dir / "main.py").write_text("print('hello')")
            (export_dir / ".env").write_text("SECRET=xyz")
            (export_dir / "secrets.json").write_text("{}")

            manifest = generate_manifest("test-id", export_dir)

            paths = [f["path"] for f in manifest["files"]]
            assert "main.py" in paths
            assert ".env" not in paths
            assert "secrets.json" not in paths

    def test_manifest_excludes_forbidden_dirs(self):
        """Test manifest excludes files in forbidden directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            (export_dir / "src").mkdir()
            (export_dir / "src" / "main.py").write_text("print('hello')")
            (export_dir / "__pycache__").mkdir()
            (export_dir / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00")

            manifest = generate_manifest("test-id", export_dir)

            paths = [f["path"] for f in manifest["files"]]
            assert any("main.py" in p for p in paths)
            assert not any("__pycache__" in p for p in paths)

    def test_manifest_detects_entrypoints(self):
        """Test manifest identifies entrypoints."""
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            (export_dir / "src").mkdir()
            (export_dir / "src" / "main.py").write_text("def main(): pass")
            (export_dir / "src" / "utils.py").write_text("def helper(): pass")

            manifest = generate_manifest("test-id", export_dir)

            assert len(manifest["entrypoints"]) >= 1
            assert any("main.py" in ep for ep in manifest["entrypoints"])

    def test_manifest_includes_file_hashes(self):
        """Test manifest includes SHA256 hashes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            content = "print('hello')"
            (export_dir / "main.py").write_text(content)

            manifest = generate_manifest("test-id", export_dir)

            file_entry = manifest["files"][0]
            assert "sha256" in file_entry
            assert len(file_entry["sha256"]) == 64  # SHA256 hex length


class TestHashFunctions:
    """Tests for hash functions."""

    def test_sha256_consistency(self):
        """Test SHA256 produces consistent results."""
        content = b"Hello, World!"
        hash1 = compute_sha256(content)
        hash2 = compute_sha256(content)
        assert hash1 == hash2

    def test_sha256_different_content(self):
        """Test SHA256 differs for different content."""
        hash1 = compute_sha256(b"Hello")
        hash2 = compute_sha256(b"World")
        assert hash1 != hash2

    def test_file_sha256(self):
        """Test file SHA256 computation."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Test content")
            temp_path = Path(f.name)

        try:
            file_hash = compute_file_sha256(temp_path)
            assert len(file_hash) == 64
        finally:
            temp_path.unlink()
