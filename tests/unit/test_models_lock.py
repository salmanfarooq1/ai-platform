from pathlib import Path

import pytest

from core.models_files import (
    MODEL_FILES_ROOT,
    ModelFileError,
    load_models_lock,
    validate_lock_licences,
    validate_model_files,
)
from core.settings import Settings
from ports.models import ModelUse


def test_lock_is_valid() -> None:
    models = load_models_lock()
    assert len(models) == 3
    for model in models:
        assert model.digest.startswith("sha256:") and len(model.digest) == 71
        assert model.use and all(isinstance(use, ModelUse) for use in model.use)


def test_lock_licences_are_osi(tmp_path: Path) -> None:
    models = load_models_lock()
    validate_lock_licences(models)
    lock = tmp_path / "bad.lock"
    lock.write_text(
        'version = 1\n[[model]]\nalias="ollama/test"\nruntime="ollama"\n'
        'digest="sha256:' + "a" * 64 + '"\nlicence="LLAMA-3"\n'
        'source="https://example.org/model"\nsize_bytes=1\nuse=["chat"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ModelFileError, match="LLAMA-3"):
        validate_lock_licences(load_models_lock(lock), {"Apache-2.0"})


def test_every_local_default_is_locked() -> None:
    models = {model.alias: set(model.use) for model in load_models_lock()}
    from config import completion_fallbacks_for_mode

    settings = Settings(mode="local", _env_file=None)
    chat_default = str(settings.llm_model)
    verifier_default = str(settings.verifier_model)
    embedding_default = str(settings.embed_model)
    completion_fallbacks = completion_fallbacks_for_mode("local")
    assert {ModelUse.CHAT, ModelUse.COMPLETION} <= models[chat_default]
    assert ModelUse.CHAT in models[verifier_default]
    locked_embedding_aliases = [
        alias for alias in models if alias == embedding_default or alias.startswith(embedding_default + ":")
    ]
    assert locked_embedding_aliases
    assert any(ModelUse.EMBEDDING in models[alias] for alias in locked_embedding_aliases)
    assert completion_fallbacks
    for completion_fallback in completion_fallbacks:
        assert ModelUse.COMPLETION in models[completion_fallback]


def test_runtime_image_copies_model_metadata_files() -> None:
    dockerfile = (MODEL_FILES_ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime_stage = dockerfile.split("AS runtime", maxsplit=1)[1]
    assert "COPY --from=builder /app/models.lock models.lock" in runtime_stage
    assert "COPY --from=builder /app/providers.register.toml providers.register.toml" in runtime_stage


def test_default_metadata_paths_are_repo_rooted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert len(load_models_lock()) == 3
    from core.models_files import load_provider_register

    assert "ollama" in load_provider_register()


def test_startup_metadata_gate_does_not_run_licence_check(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.models_files

    def unexpected_licence_check(*args: object, **kwargs: object) -> None:
        pytest.fail("licence checks belong to CI, not runtime startup")

    monkeypatch.setattr(core.models_files, "validate_lock_licences", unexpected_licence_check)
    validate_model_files(Settings(mode="local", _env_file=None))
