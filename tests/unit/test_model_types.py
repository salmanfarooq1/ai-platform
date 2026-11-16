from dataclasses import FrozenInstanceError

import pytest

from evidence.extensions import validate_extensions
from ports.models import ModelIdentity, ModelRoute, ModelUse, ResolvedModel, SecretRef

_DIGEST = "sha256:" + "a" * 64
_ROUTE = "sha256:" + "b" * 64


def _identity(source: str = "local", *, digest: str | None = _DIGEST, provider_model_id: str | None = None) -> ModelIdentity:
    return ModelIdentity(
        alias="ollama/qwen3:4b", provider="ollama", source=source, digest=digest,
        provider_model_id=provider_model_id, processing_scope="eu", region="eu", storage_geography=None,
    )  # type: ignore[arg-type]


def test_identity_route_resolved_are_frozen() -> None:
    identity = _identity()
    route = ModelRoute(identity=identity, endpoint="http://ollama:11434", credential=None,
                       params={"num_ctx": 8192, "nested": {"value": "fixed"}})
    resolved = ResolvedModel(identity=identity, route=route, use=ModelUse.CHAT, price_ref=None, data_use="unknown")
    with pytest.raises(FrozenInstanceError):
        identity.alias = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        route.endpoint = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        resolved.use = ModelUse.COMPLETION  # type: ignore[misc]
    with pytest.raises(TypeError):
        route.params["temperature"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        route.params["nested"]["value"] = "changed"  # type: ignore[index]
    assert isinstance(hash(route), int)
    assert isinstance(hash(resolved), int)
    same_route = ModelRoute(identity, "http://ollama:11434", None,
                            {"num_ctx": 8192, "nested": {"value": "fixed"}})
    assert route == same_route
    assert hash(route) == hash(same_route)


def test_identity_needs_digest_or_provider_model_id() -> None:
    with pytest.raises(ValueError):
        _identity(digest=None)
    with pytest.raises(ValueError):
        _identity("hosted", digest=None)
    with pytest.raises(ValueError):
        _identity("hosted", provider_model_id="versioned-model")
    with pytest.raises(ValueError):
        ModelIdentity("hosted/model", "hosted", "hosted", _DIGEST, "id", "eu", "eu", None)  # type: ignore[arg-type]


def test_extension_matches_registered_schema() -> None:
    identities = (
        _identity(),
        ModelIdentity("openai/gpt", "openai", "hosted", None, "gpt-version", "us", "us", "us"),
    )
    for identity in identities:
        for phase in ("admission", "attempt"):
            route = ModelRoute(identity, "https://models.example/v1", None, {})
            resolved = ResolvedModel(identity, route, ModelUse.CHAT, None, "unknown")
            extension = resolved.as_extension(phase)  # type: ignore[arg-type]
            validate_extensions({"model": extension})
            with pytest.raises(ValueError):
                validate_extensions({"model": {**extension, "unexpected": "value"}})
            with pytest.raises(ValueError):
                validate_extensions({"model": {**extension, "route": ""}})


def test_resolved_identity_must_match_route() -> None:
    identity = _identity()
    other_identity = _identity(digest="sha256:" + "c" * 64)
    route = ModelRoute(other_identity, "https://models.example/v1", None, {})
    with pytest.raises(ValueError):
        ResolvedModel(identity, route, ModelUse.CHAT, None, "unknown")


def test_stages_extension_schema() -> None:
    stage_names = ("principal", "module", "boundary", "model", "policy", "guardrails", "rate", "budget", "cost")
    stages = [
        {"stage": name, "status": "passed", "reason": None, "duration_us": 1}
        for name in stage_names
    ]
    validate_extensions({"stages": stages})

    invalid_values = []
    invalid_values.append([{**stages[0], "stage": "unknown"}, *stages[1:]])
    invalid_values.append([{**stages[0], "status": "unknown"}, *stages[1:]])
    invalid_values.append([{key: value for key, value in stages[0].items() if key != "duration_us"}, *stages[1:]])
    invalid_values.append([{**stages[0], "duration_us": -1}, *stages[1:]])
    invalid_values.append([{**stages[0], "extra": "value"}, *stages[1:]])
    for value in invalid_values:
        with pytest.raises(ValueError):
            validate_extensions({"stages": value})
    with pytest.raises(ValueError):
        validate_extensions({"stages": [*stages, stages[-1]]})


def test_fingerprint_changes_with_any_route_field() -> None:
    identity = _identity()
    base = ModelRoute(identity, "https://models.example/v1", SecretRef("env", "KEY"), {"temperature": 0.1})
    changed_endpoint = ModelRoute(identity, "https://other.example/v1", SecretRef("env", "KEY"), {"temperature": 0.1})
    changed_secret = ModelRoute(identity, "https://models.example/v1", SecretRef("env", "OTHER_KEY"), {"temperature": 0.1})
    changed_param = ModelRoute(identity, "https://models.example/v1", SecretRef("env", "KEY"), {"temperature": 0.2})
    changed_identity = ModelRoute(_identity(digest="sha256:" + "c" * 64), "https://models.example/v1", SecretRef("env", "KEY"), {"temperature": 0.1})
    assert len({base.fingerprint, changed_endpoint.fingerprint, changed_secret.fingerprint,
                changed_param.fingerprint, changed_identity.fingerprint}) == 5
