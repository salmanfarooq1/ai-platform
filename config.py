import os
from pathlib import Path

from dotenv import load_dotenv

# ==========================================
# ENVIRONMENT INITIALIZATION
# ==========================================

# Load .env.local if it exists, otherwise fallback to .env
env_local = Path(".env.local")
if env_local.exists():
    load_dotenv(dotenv_path=".env.local", override=True)
else:
    load_dotenv()

# ==========================================
# RETRIEVAL AND VECTOR CAPABILITIES
# ==========================================

# Embedding dimensions: 768 is the universal compatibility point.
# Ollama nomic embed text: 768 native
# Azure text embedding 3 small: 1536 native, called with dimensions=768
# GCP text embedding 005: 768 native
# GCP gemini embedding 001: 3072 native, called with outputDimensionality=768
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 768))

# Minimum vector score (cosine similarity) to consider a chunk relevant.
# 0.0 means orthogonal/opposite vectors are filtered out.
# Kept here rather than as a literal in the SQL so switching embedding models later
# is a one line change, not a SQL edit + redeploy.
MIN_VECTOR_SCORE = 0.0

# ==========================================
# AGENT AND SYSTEM REGISTRIES
# ==========================================

# Namespaces available to search, with a short description of each.
# The agent's list_namespaces tool reads this directly, so adding a namespace
# here is enough. No prompt or code change needed elsewhere.
NAMESPACE_REGISTRY = {
    "legal": "GDPR, CCPA, HIPAA, and other data protection regulations",
    "kyc_aml": "KYC, AML, and Bank Secrecy Act documentation",
    "default": "Uncategorized or general compliance documents",
}

# ==========================================
# DEPLOYMENT MODE
# ==========================================

# MODE controls which external services the platform connects to.
# "local" → Docker Compose only. Zero cloud dependency. Works offline.
# "demo"  → Free cloud services (Neon, Upstash, Groq). Permanent URL, no credit card.
# "prod"  → Azure full stack. GPT 4o, Azure PostgreSQL, Azure Redis.

# NOTE: in prod mode, Azure's text embedding 3 small (1536 native) must be called with dimensions=768.
# GCP's text embedding 005 outputs 768 natively (no reduction needed).
MODE = os.getenv("MODE", "local")

# ==========================================
# EXTERNAL SERVICE CONFIGURATIONS
# ==========================================

LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", {
        "local": "groq/meta-llama/llama-4-scout-17b-16e-instruct", # For complex reasoning
        "demo":  "groq/meta-llama/llama-4-scout-17b-16e-instruct",
        "prod":  "azure/gpt-4o",
    }.get(MODE, "groq/meta-llama/llama-4-scout-17b-16e-instruct")),

    # Note: Groq has no embedding API (Ollama serves embeddings for both local and demo).
    # CAVEAT: In demo mode, if Ollama goes down, there is no embedding fallback.
    # The fallbacks list below only covers LLM completion, not embeddings.
    "embedding_model": os.getenv("EMBED_MODEL", {
        "local": "ollama/nomic-embed-text",
        "demo":  "ollama/nomic-embed-text",
        "prod":  "azure/text-embedding-3-small",
    }.get(MODE, "ollama/nomic-embed-text")),

    "api_base": os.getenv("AZURE_OAI_BASE", None),
    "api_key":  os.getenv("AZURE_OAI_KEY",  None),
    "groq_key": os.getenv("GROQ_API_KEY",   None),

    # Simple queries route to fallbacks[0]
    "fallbacks": ["ollama/qwen2.5"] if MODE == "local" else ["ollama/llama3"],
}

DATABASE_CONFIG = {
    "url": os.getenv("DATABASE_URL", {
        "local": "postgresql://postgres:postgres@localhost:5432/rag_platform",
        "demo":  "postgresql://user:pass@ep-xxx.neon.tech/rag_platform?sslmode=require",
        "prod":  "postgresql://user:pass@ai-platform.postgres.database.azure.com/rag_platform",
    }.get(MODE, "postgresql://postgres:postgres@localhost:5432/rag_platform")),
    "pool_size": 5 if MODE == "demo" else 20,
}

CACHE_CONFIG = {
    "url": os.getenv("REDIS_URL", {
        "local": "redis://localhost:6379",
        "demo":  "redis://default:xxx@xxx.upstash.io:6379",
        "prod":  "rediss://xxx.redis.cache.windows.net:6380",
    }.get(MODE, "redis://localhost:6379")),
}

# ==========================================
# FEATURE FLAGS AND LIMITS
# ==========================================

FEATURES = {
    "reranker_enabled": MODE != "demo",  # disabled on Koyeb free tier (512MB RAM OOM guard)
    "otel_enabled": True,
    "azure_monitor": MODE == "prod",
    "verifier_enabled": True,  # Enables the synthesis verifier loop in the agent
}

# Input and Output Guardrails configuration
GUARDRAIL_CONFIG = {
    # Maximum query character length (Default: 1000 characters)
    "max_query_length": int(os.getenv("MAX_QUERY_LENGTH", 1000)),
    # Self reported LLM confidence floor for flagging (Default: 0.45)
    "confidence_floor": float(os.getenv("CONFIDENCE_FLOOR", 0.45)),
}
