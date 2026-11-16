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
def test_public_preview_configuration(monkeypatch):
    monkeypatch.setenv("MODE", "public-preview")
    # Sprint 002: hosted modes require explicit DSNs (no placeholder defaults).
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/app")
    monkeypatch.setenv("REDIS_URL", "redis://cache.example.test:6379")
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")  # hosted modes need one (Sprint 008)
    monkeypatch.setenv("DEPLOY_REGION", "us")
    reloaded = importlib.reload(config)
    assert reloaded.DATABASE_CONFIG["pool_size"] == 5


@pytest.mark.unit
def test_unknown_mode_raises(monkeypatch):
    monkeypatch.setenv("MODE", "demo")
    with pytest.raises(ValueError, match="public-preview"):
        importlib.reload(config)


@pytest.mark.unit
def test_real_env_beats_env_local(tmp_path, monkeypatch):
    from core.settings import get_settings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local").write_text("MODE=prod\n")
    monkeypatch.setenv("MODE", "local")
    get_settings.cache_clear()
    assert get_settings().mode == "local"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["local", "public-preview"])
def test_modes_with_env_local_present(tmp_path, monkeypatch, mode):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local").write_text("LOG_LEVEL=DEBUG\n")
    monkeypatch.setenv("MODE", mode)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/app")
    monkeypatch.setenv("REDIS_URL", "redis://cache.example.test:6379")
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("DEPLOY_REGION", "us")
    assert importlib.reload(config).MODE == mode
