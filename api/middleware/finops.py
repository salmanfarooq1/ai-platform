"""
FinOps middleware — cost calculation and persistent usage logging.

Runs after the route handler returns, and books the tokens used against the tenant's daily budget
(`gateway.limits.record_usage`; the budget check itself is a gateway stage). Reads request.state.usage
(set by /search and /agent/query routes), calculates dollar cost
from MODEL_PRICING in config.py, stamps response headers, and persists
the record to Postgres via the usage writer service.

The DB write is fire-and-forget: if Postgres is temporarily unreachable,
the header is still stamped and the request still succeeds.
"""
import asyncio
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.services.usage import record_usage
from config import MODEL_PRICING
from gateway.limits import record_usage as book_tokens

logger = logging.getLogger("api.finops")


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Dollar cost of one request from MODEL_PRICING. Ollama models and unknown models cost 0."""
    if model.startswith("ollama/"):
        rates = {"input": 0.0, "output": 0.0}
    elif model not in MODEL_PRICING:
        logger.warning(
            "[finops] Unknown model '%s' not in MODEL_PRICING. "
            "Cost reported as $0.00. Add an entry to config.py.",
            model,
        )
        rates = {"input": 0.0, "output": 0.0}
    else:
        rates = MODEL_PRICING[model]
    return (prompt_tokens / 1_000_000) * rates["input"] + (completion_tokens / 1_000_000) * rates["output"]


class FinOpsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        usage = getattr(request.state, "usage", None)
        cost_usd = 0.0

        if usage:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            model = usage.get("model", "unknown")

            cost_usd = compute_cost(model, prompt_tokens, completion_tokens)

        response.headers["X-Cost-USD"] = f"{cost_usd:.6f}"

        # Headers the gateway stages asked for (rate limit remaining).
        for name, value in getattr(request.state, "gateway_headers", {}).items():
            response.headers[name] = value

        if usage:
            response.headers["X-Tokens-In"] = str(usage.get("prompt_tokens", 0))
            response.headers["X-Tokens-Out"] = str(usage.get("completion_tokens", 0))

            request_id = str(getattr(request.state, "request_id", "unknown"))
            response.headers["X-Query-ID"] = request_id

            # An agent run that a worker finished has booked its own tokens and usage row (`usage_booked`).
            booked = bool(getattr(request.state, "usage_booked", False))
            logger.info(
                "[finops] %s cost=$%.6f model=%s tokens=%d+%d",
                request_id,
                cost_usd,
                usage.get("model", "unknown"),
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

            pool = getattr(request.app.state, "db_pool", None)
            principal = getattr(request.state, "principal", None)
            runtime = getattr(request.app.state, "gateway_runtime", None)
            total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
            if booked:
                for name, value in (usage.get("budget_headers") or {}).items():
                    response.headers[name] = value
            if runtime and principal and total_tokens > 0 and not booked:
                # Book the tokens against the tenant's daily budget (best effort: the work is already done).
                for name, value in (await book_tokens(runtime, principal.tenant_id, total_tokens)).items():
                    response.headers[name] = value
            if pool and principal and not booked:
                asyncio.create_task(
                    record_usage(
                        pool=pool,
                        tenant_id=principal.tenant_id,
                        request_id=request_id,
                        endpoint=request.url.path,
                        namespace=usage.get("namespace", "global"),
                        model=usage.get("model", "unknown"),
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        cost_usd=cost_usd,
                        routing_decision=usage.get("routing_decision", ""),
                    )
                )

        return response
