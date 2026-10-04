"""Unit tests for MODE handling in config.py."""
import importlib

import pytest

import config


@pytest.fixture(autouse=True)
def restore_config(monkeypatch):
    """Reload config with the original environment after each test."""
    yield
    monkeypatch.undo()
    importlib.reload(config)


@pytest.mark.unit
def test_public_preview_disables_reranker(monkeypatch):
    monkeypatch.setenv("MODE", "public-preview")
    # Sprint 002: hosted modes require explicit DSNs (no placeholder defaults).
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/app")
    monkeypatch.setenv("REDIS_URL", "redis://cache.example.test:6379")
    reloaded = importlib.reload(config)
    assert reloaded.FEATURES["reranker_enabled"] is False
    assert reloaded.DATABASE_CONFIG["pool_size"] == 5


@pytest.mark.unit
def test_local_enables_reranker(monkeypatch):
    monkeypatch.setenv("MODE", "local")
    reloaded = importlib.reload(config)
    assert reloaded.FEATURES["reranker_enabled"] is True


@pytest.mark.unit
def test_unknown_mode_raises(monkeypatch):
    monkeypatch.setenv("MODE", "demo")
    with pytest.raises(ValueError, match="public-preview"):
        importlib.reload(config)
