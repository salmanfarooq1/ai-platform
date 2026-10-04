"""Tests for FinOps middleware pricing logic."""

import pytest

from api.middleware.finops import compute_cost
from config import LLM_CONFIG, MODEL_PRICING


def test_model_pricing_has_required_models():
    """All models used in LLM_CONFIG must have pricing entries."""
    for model in ("gemini/gemini-3.5-flash-lite", "azure/gpt-4o"):
        assert model in MODEL_PRICING, f"Missing pricing for {model}"
    assert LLM_CONFIG["model"] in MODEL_PRICING


def test_model_pricing_values_are_positive():
    """Pricing rates must be non-negative floats."""
    for model, rates in MODEL_PRICING.items():
        assert "input" in rates, f"{model} missing 'input' rate"
        assert "output" in rates, f"{model} missing 'output' rate"
        assert rates["input"] >= 0, f"{model} input rate is negative"
        assert rates["output"] >= 0, f"{model} output rate is negative"


def test_compute_cost_matches_pricing_table():
    """compute_cost is the function FinOpsMiddleware uses. Expected values are hand-computed per million tokens."""
    # gpt-oss-120b: $0.11 in, $0.34 out per million tokens
    assert compute_cost("openai/gpt-oss-120b", 1_000_000, 0) == pytest.approx(0.11)
    assert compute_cost("openai/gpt-oss-120b", 0, 1_000_000) == pytest.approx(0.34)
    assert compute_cost("openai/gpt-oss-120b", 1000, 500) == pytest.approx(0.00028)
    # gpt-4o: $2.50 in, $10.00 out
    assert compute_cost("azure/gpt-4o", 2_000_000, 100_000) == pytest.approx(6.0)


def test_compute_cost_zero_tokens_is_free():
    assert compute_cost("azure/gpt-4o", 0, 0) == 0.0


def test_compute_cost_free_tier_gemini_is_zero():
    assert compute_cost("gemini/gemini-3.5-flash-lite", 5_000_000, 5_000_000) == 0.0


def test_ollama_models_cost_zero_even_if_unpriced():
    assert compute_cost("ollama/qwen2.5", 10_000_000, 10_000_000) == 0.0


def test_unknown_model_costs_zero_and_warns(caplog):
    with caplog.at_level("WARNING", logger="api.finops"):
        assert compute_cost("made-up/model", 1000, 1000) == 0.0
    assert "made-up/model" in caplog.text


def test_compute_cost_follows_a_patched_pricing_table(monkeypatch):
    monkeypatch.setitem(MODEL_PRICING, "test/model", {"input": 1.0, "output": 2.0})
    assert compute_cost("test/model", 3_000_000, 1_000_000) == pytest.approx(5.0)


def test_ollama_models_are_not_in_pricing():
    """Models starting with 'ollama/' are handled as 0 by compute_cost and need no pricing entry."""
    for model in MODEL_PRICING:
        assert not model.startswith("ollama/"), f"Ollama model {model} should not have pricing"
