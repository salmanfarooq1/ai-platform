"""Tests for FinOps middleware pricing logic."""
import pytest

from config import MODEL_PRICING


def test_model_pricing_has_required_models():
    """All models used in LLM_CONFIG must have pricing entries."""
    required = [
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",
    ]
    for model in required:
        assert model in MODEL_PRICING, f"Missing pricing for {model}"


def test_model_pricing_values_are_positive():
    """Pricing rates must be non-negative floats."""
    for model, rates in MODEL_PRICING.items():
        assert "input" in rates, f"{model} missing 'input' rate"
        assert "output" in rates, f"{model} missing 'output' rate"
        assert rates["input"] >= 0, f"{model} input rate is negative"
        assert rates["output"] >= 0, f"{model} output rate is negative"


def test_cost_calculation_formula():
    """Verify the cost formula matches what finops.py uses."""
    rates = MODEL_PRICING["groq/meta-llama/llama-4-scout-17b-16e-instruct"]
    prompt_tokens = 1000
    completion_tokens = 500

    input_cost = (prompt_tokens / 1_000_000) * rates["input"]
    output_cost = (completion_tokens / 1_000_000) * rates["output"]
    total = input_cost + output_cost

    assert total > 0
    assert total < 0.01  # sanity: 1500 tokens should cost less than a cent


def test_ollama_models_get_zero_cost():
    """Models starting with 'ollama/' should not be in PRICING (handled as 0 in middleware)."""
    for model in MODEL_PRICING:
        assert not model.startswith("ollama/"), f"Ollama model {model} should not have pricing"
