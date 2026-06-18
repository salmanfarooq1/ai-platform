from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import logging

logger = logging.getLogger("api.finops")

# Prices are per 1,000,000 tokens
PRICING = {
    "azure/gpt-4o":         {"input": 2.50, "output": 10.00},
    "groq/llama-3.1-70b":   {"input": 0.59, "output": 0.79},
    "ollama/llama3":         {"input": 0.00, "output": 0.00},
}

class FinOpsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. run the route, and wait for response by LLM.
        response = await call_next(request)
        
        # 2. Check if the route attached any token usage data to the request state.
        usage = getattr(request.state, "usage", None)
        
        cost_usd = 0.0
        
        if usage:
            # 1. Extract tokens and model, safely defaulting to 0 or "unknown"
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            model = usage.get("model", "unknown")
            
            # 2. Look up the pricing rates. Default to $0 if model isn't in our dictionary.
            rates = PRICING.get(model, {"input": 0.0, "output": 0.0})
            
            # 3. Calculate the dollar cost
            input_cost = (prompt_tokens / 1_000_000) * rates["input"]
            output_cost = (completion_tokens / 1_000_000) * rates["output"]
            
            cost_usd = input_cost + output_cost
            
        # 3. Stamp the headers
        response.headers["X-Cost-USD"] = f"{cost_usd:.6f}"
        
        if usage:
            response.headers["X-Tokens-In"] = str(usage.get("prompt_tokens", 0))
            response.headers["X-Tokens-Out"] = str(usage.get("completion_tokens", 0))
            
            # Log the cost so we have a permanent record!
            logger.info(f"Query ID {getattr(request.state, 'request_id', 'unknown')} cost ${cost_usd:.6f}")
            
        return response
