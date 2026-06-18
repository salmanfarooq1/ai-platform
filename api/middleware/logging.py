import uuid
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# middleware sits between the incoming request and route handler, and then outgoing response.
# we use it to add request IDs, measure latency, and log requests/responses.
# it is crucial for debugging ( request-id ) and performance monitoring ( latency ).

# Configure basic logging for the console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Generate unique ID string
        request_id = uuid.uuid4().hex
        
        # 2. Attach it to the request state so inner routes can see it
        request.state.request_id = request_id
        
        # 3. Hand off the request to the rest of the API
        response = await call_next(request)
        
        # 4. Stamp the response headers before it leaves the server
        response.headers["X-Request-ID"] = request_id
        return response

class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Start the time counter
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        # 2. calculate milliseconds
        process_time = (time.perf_counter() - start_time) * 1000
        
        # 3. Stamp the header
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        return response

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Log the incoming request method (POST) and path (/ingest)
        logger.info(f"Incoming: {request.method} {request.url.path}")
        
        response = await call_next(request)
        
        # 2. Log the final outcome
        logger.info(f"Outgoing: {request.method} {request.url.path} - Status: {response.status_code}")
        return response
