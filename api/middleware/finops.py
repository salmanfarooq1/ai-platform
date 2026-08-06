"""
FinOps middleware — cost calculation and persistent usage logging.

Runs after the route handler returns. Reads request.state.usage
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

logger = logging.getLogger("api.finops")


class FinOpsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        usage = getattr(request.state, "usage", None)
        cost_usd = 0.0

        if usage:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            model = usage.get("model", "unknown")

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

            input_cost = (prompt_tokens / 1_000_000) * rates["input"]
            output_cost = (completion_tokens / 1_000_000) * rates["output"]
            cost_usd = input_cost + output_cost

        response.headers["X-Cost-USD"] = f"{cost_usd:.6f}"

        if usage:
            response.headers["X-Tokens-In"] = str(usage.get("prompt_tokens", 0))
            response.headers["X-Tokens-Out"] = str(usage.get("completion_tokens", 0))

            request_id = str(getattr(request.state, "request_id", "unknown"))
            response.headers["X-Query-ID"] = request_id

            logger.info(
                "[finops] %s cost=$%.6f model=%s tokens=%d+%d",
                request_id,
                cost_usd,
                usage.get("model", "unknown"),
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

            pool = getattr(request.app.state, "db_pool", None)
            if pool:
                asyncio.create_task(
                    record_usage(
                        pool=pool,
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
