# ============================================================================
# Stage 1: Builder — install Poetry, resolve deps, build the virtualenv
# ============================================================================
FROM python:3.11-slim-bookworm AS builder

# Poetry needs these env vars to behave correctly in CI/Docker:
#   POETRY_NO_INTERACTION: never prompt for input
#   POETRY_VIRTUALENVS_IN_PROJECT: create .venv inside the project dir
#     (so we can COPY it to the runtime stage without guessing the path)
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

# Install Poetry. pipx is the recommended way to install Poetry globally
# without polluting the project's virtualenv.
RUN pip install --no-cache-dir pipx && \
    pipx install poetry

# Make pipx-installed binaries available on PATH
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy only dependency files first. Docker caches layers by content hash.
# If pyproject.toml and poetry.lock have not changed, Docker reuses the
# cached layer from the previous build. This means `poetry install` only
# runs when dependencies actually change — not on every code change.
COPY pyproject.toml poetry.lock ./

# Install runtime dependencies only (no dev/test deps in production image).
# --no-root: don't install the project itself yet (we haven't copied the code).
RUN poetry install --only main --no-root

# Now copy the application code. This layer changes on every code change,
# but the dependency layer above is cached.
COPY . .

# ============================================================================
# Stage 2: Runtime — lean image with only the virtualenv and app code
# ============================================================================
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy the virtualenv from the builder stage.
# This contains all installed packages (fastapi, litellm, sentence-transformers, etc.)
COPY --from=builder /app/.venv .venv

# Copy application code
COPY --from=builder /app/api api/
COPY --from=builder /app/core core/
COPY --from=builder /app/config.py config.py
COPY --from=builder /app/data data/

# Activate the virtualenv by prepending it to PATH.
# This is the Docker equivalent of `source .venv/bin/activate`.
ENV PATH="/app/.venv/bin:$PATH"

# Expose the port uvicorn will listen on
EXPOSE 8000

# Health check — Docker and Fly.io use this to know if the container is alive.
# The /health endpoint checks DB + Redis connectivity and returns 200 or 503.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run uvicorn with production settings.
# --host 0.0.0.0: listen on all interfaces (required inside a container)
# --workers 2: two worker processes for basic concurrency
# --timeout-keep-alive 65: slightly above the typical 60s load balancer timeout
#   to prevent the LB from sending requests to a closing connection
CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--timeout-keep-alive", "65"]
