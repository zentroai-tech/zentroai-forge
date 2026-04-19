"""Tests for backend config.py — PR_001 security checks."""

import pytest

from agent_compiler.config import get_settings


class TestCORSConfig:
    """CORS methods must never use a wildcard with credentials enabled."""

    def test_cors_methods_no_wildcard(self):
        settings = get_settings()
        assert "*" not in settings.cors_allow_methods

    def test_cors_methods_include_expected(self):
        settings = get_settings()
        for method in ["GET", "POST", "PUT", "DELETE"]:
            assert method in settings.cors_allow_methods

    def test_cors_methods_include_options(self):
        """OPTIONS must be present for preflight requests."""
        settings = get_settings()
        assert "OPTIONS" in settings.cors_allow_methods

    def test_cors_methods_include_patch(self):
        settings = get_settings()
        assert "PATCH" in settings.cors_allow_methods
