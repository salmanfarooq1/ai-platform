from typing import Any

from core.settings import get_settings

# ==========================================
# ENVIRONMENT INITIALIZATION
# ==========================================

# Every value below is built from the validated Settings object (core/settings.py).
# A bad or missing value raises SettingsError on import, so startup fails fast.
# The cache is cleared first so importlib.reload(config) re-reads the environment.
get_settings.cache_clear()
_settings = get_settings()

# ==========================================
# RETRIEVAL AND VECTOR CAPABILITIES
# ==========================================

# Embedding dimensions: 768 is the universal compatibility point.
# Ollama nomic embed text: 768 native
# Azure text embedding 3 small: 1536 native, called with dimensions=768
# GCP text embedding 005: 768 native
# GCP gemini embedding 001: 3072 native, called with outputDimensionality=768
EMBEDDING_DIM = _settings.embedding_dim

# Minimum vector score (cosine similarity) to consider a chunk relevant.
# 0.0 means orthogonal/opposite vectors are filtered out.
# Kept here rather than as a literal in the SQL so switching embedding models later
# is a one line change, not a SQL edit + redeploy.
MIN_VECTOR_SCORE = 0.0

# Knowledge bases (formerly a global namespace registry here) are tenant-owned rows in the `knowledge_bases` table.

# ==========================================
# DEPLOYMENT MODE
# ==========================================

# MODE controls which external services the platform connects to.
# "local" → Docker Compose only. Zero cloud dependency. Works offline.
# "public-preview" → Free cloud services (Neon, Upstash, Groq). Permanent URL, no credit card.
# "prod"  → Azure full stack. GPT 4o, Azure PostgreSQL, Azure Redis.

# NOTE: in prod mode, Azure's text embedding 3 small (1536 native) must be called with dimensions=768.
# GCP's text embedding 005 outputs 768 natively (no reduction needed).
MODE = _settings.mode

# ==========================================
# EXTERNAL SERVICE CONFIGURATIONS
# ==========================================

LLM_CONFIG: dict[str, Any] = {
    "model": _settings.llm_model,

    # Note: Groq has no embedding API, so embeddings come from a separate provider.
    # local -> Ollama on the host (nomic-embed-text, 768 native).
    # public-preview -> Gemini gemini-embedding-001 (3072 native, truncated to 768).
    #          Public-preview runs on a 512MB Render instance with no Ollama sidecar to
    #          talk to, so the embedding provider has to be a hosted API.
    #          Requires GEMINI_API_KEY. Note that text-embedding-004 is retired
    #          and 404s on current keys.
    # Embedding fallbacks (Sprint 006): EMBED_FALLBACK_MODELS is an ordered list the embedding adapter
    # (adapters/litellm_embeddings.py) tries when the primary fails, refusing any model whose width is not
    # EMBEDDING_DIM. The "fallbacks" list below is only for LLM completion.
    #
    # Every mode ends up at EMBEDDING_DIM (768) to match the VECTOR(768) column
    # in the Alembic baseline (migrations/versions/0001_baseline.py). Where the provider is wider than that,
    # adapters/litellm_embeddings.py requests the narrower width and renormalizes.
    # Switching to a provider that cannot emit 768 means a schema change and a
    # full re-ingest.
    "embedding_model": _settings.embed_model,

    "api_base": _settings.azure_oai_base,
    "api_key":  _settings.azure_oai_key,
    "groq_key": _settings.groq_api_key,

    # Simple queries route to fallbacks[0]
    "fallbacks": ["ollama/qwen2.5"] if MODE == "local" else ["ollama/llama3"],
}

DATABASE_CONFIG: dict[str, Any] = {
    "url": _settings.database_dsn,
    "pool_size": 5 if MODE == "public-preview" else 20,
}

CACHE_CONFIG: dict[str, Any] = {
    "url": _settings.redis_dsn,
}

# ==========================================
# FEATURE FLAGS AND LIMITS
# ==========================================

FEATURES: dict[str, bool] = {
    "reranker_enabled": MODE != "public-preview",  # disabled on Render free tier (512MB RAM OOM guard)
    "otel_enabled": True,
    "azure_monitor": MODE == "prod",
    "verifier_enabled": True,  # Enables the synthesis verifier loop in the agent
}

# Input and Output Guardrails configuration
GUARDRAIL_CONFIG: dict[str, Any] = {
    # Maximum query character length (Default: 1000 characters)
    "max_query_length": _settings.max_query_length,
    # Self reported LLM confidence floor for flagging (Default: 0.45)
    "confidence_floor": _settings.confidence_floor,
}

# LLM token pricing in USD per million tokens.
# Update this dict when providers change rates, or replace with
# a dynamic fetch script (see OBS-06 in notes_and_obs.md).
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Gemini free tier is $0. Paid-tier rates are not recorded here (see planning/QUESTIONS.md B2).
    "gemini/gemini-3.5-flash-lite":                        {"input": 0.0,   "output": 0.0},
    "azure/gpt-4o":                                        {"input": 2.50,  "output": 10.00},
    "groq/llama-3.1-70b-versatile":                        {"input": 0.59,  "output": 0.79},
    # LiteLLM strips the provider prefix (groq/) from model names in usage
    # data, so finops receives "openai/gpt-oss-120b". Alias maps to same rate.
    "openai/gpt-oss-120b":                                 {"input": 0.11,  "output": 0.34},
}

# ==========================================
# RATE LIMITING AND BUDGET CONSTANTS
# ==========================================

# Fixed-window rate limiting — requests per window.
RATE_LIMIT_REQUESTS = _settings.rate_limit_requests
RATE_LIMIT_WINDOW_SECONDS = _settings.rate_limit_window_seconds

# Daily token budget per tenant.
# At Groq's llama-4-scout pricing ($0.11/M input + $0.34/M output),
# 500K tokens costs roughly $0.11. Generous for development, tight enough
# to catch runaway loops.
DEFAULT_DAILY_TOKEN_BUDGET = _settings.daily_token_budget
