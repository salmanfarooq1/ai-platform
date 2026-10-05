"""Model prices, and the rule for a model that has none (Sprint 008, QA finding M3).

An unpriced model used to cost 0, so it could never trip the daily cost cap. Now it is costed at the highest known rate
(the highest input and the highest output price in the table), so a missing price can only make the cap trip sooner.
Local Ollama models are free. In a hosted mode the platform refuses to start when a model it is configured to call has
no price at all.
"""
import logging
from collections.abc import Iterable, Mapping

logger = logging.getLogger("core.pricing")

FREE = {"input": 0.0, "output": 0.0}


def rates_for(table: Mapping[str, Mapping[str, float]], model: str) -> Mapping[str, float]:
    """USD per million tokens for `model`: its own entry, zero for `ollama/` models, else the highest known rate."""
    if model.startswith("ollama/"):
        return FREE
    if model in table:
        return table[model]
    logger.warning("[pricing] model '%s' has no price: costed at the highest known rate. Add it to MODEL_PRICING.", model)
    if not table:
        return FREE
    return {"input": max(r["input"] for r in table.values()), "output": max(r["output"] for r in table.values())}


def unpriced(table: Mapping[str, Mapping[str, float]], models: Iterable[str | None]) -> list[str]:
    return sorted({m for m in models if m and not m.startswith("ollama/") and m not in table})


def check_priced(table: Mapping[str, Mapping[str, float]], mode: str, models: Iterable[str | None]) -> None:
    """Hosted modes: raise when a configured chat or embedding model has no price. Local mode never raises."""
    missing = unpriced(table, models)
    if mode != "local" and missing:
        raise ValueError(f"no price in MODEL_PRICING for configured model(s): {', '.join(missing)}")
