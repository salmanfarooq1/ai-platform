"""Sprint 008 QA fixes: unpriced models (M3), the method label (M4) and the signing key as a secret (L2)."""
import pytest
from starlette.types import Scope

import config
from api.middleware.metrics import method_label
from core.pricing import check_priced, rates_for
from core.settings import Settings, get_settings

pytestmark = pytest.mark.unit

TABLE = {"a/cheap": {"input": 1.0, "output": 2.0}, "b/dear": {"input": 10.0, "output": 30.0}, "c/mixed": {"input": 5.0, "output": 40.0}}


def test_m3_an_unpriced_model_is_costed_at_the_highest_known_rate():
    assert rates_for(TABLE, "a/cheap") == {"input": 1.0, "output": 2.0}
    assert dict(rates_for(TABLE, "never/heard")) == {"input": 10.0, "output": 40.0}  # highest input and highest output
    assert dict(rates_for(TABLE, "ollama/anything")) == {"input": 0.0, "output": 0.0}  # local models stay free


def test_m3_hosted_modes_refuse_a_configured_model_with_no_price_and_local_does_not():
    check_priced(TABLE, "prod", ["a/cheap", "b/dear", None])
    check_priced(TABLE, "public-preview", ["ollama/x"])
    for mode in ("prod", "public-preview"):
        with pytest.raises(ValueError, match="no price in MODEL_PRICING.*never/heard"):
            check_priced(TABLE, mode, ["a/cheap", "never/heard"])
    check_priced(TABLE, "local", ["never/heard"])


def test_m3_the_default_models_of_every_mode_have_a_price():
    from core.settings import _EMBED_MODEL_DEFAULTS, _LLM_MODEL_DEFAULTS

    for mode in ("public-preview", "prod"):
        check_priced(config.MODEL_PRICING, mode, [_LLM_MODEL_DEFAULTS[mode], _EMBED_MODEL_DEFAULTS[mode]])


@pytest.mark.parametrize("method, label", [("GET", "GET"), ("post", "POST"), ("OPTIONS", "OPTIONS"), ("FOO", "OTHER"), ("PROPFIND", "OTHER"), ("x" * 50, "OTHER")])
def test_m4_methods_outside_the_standard_set_share_one_label(method, label):
    scope: Scope = {"type": "http", "method": method}
    assert method_label(scope) == label


def test_l2_the_signing_key_is_a_secret_and_is_not_printed():
    key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    settings = Settings(mode="local", receipt_signing_key=key)  # type: ignore[arg-type]
    assert key not in repr(settings) and key not in str(settings) and key not in str(settings.model_dump())
    assert str(settings.receipt_signing_key) == "**********"
    assert settings.signing_key_text == key
    assert Settings(mode="local").signing_key_text == "" and get_settings().receipt_signing_key is None
