from dotenv import load_dotenv
import os

load_dotenv()

# Embedding dimensions: 768 is the universal compatibility point.
# - Ollama nomic-embed-text: 768 native
# - Azure text-embedding-3-small: 1536 native, called with dimensions=768
# - GCP text-embedding-005: 768 native
# - GCP gemini-embedding-001: 3072 native, called with outputDimensionality=768
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 768))

#--------- DEPLOYMENT MODES CONFIG ---------#

# MODE controls which external services the platform connects to.
# "local" → Docker Compose only. Zero cloud dependency. Works offline.
# "demo"  → Free cloud services (Neon, Upstash, Groq). Permanent URL, no credit card.
# "prod"  → Azure full stack. GPT-4o, Azure PostgreSQL, Azure Redis.

# NOTE: in prod mode, Azure's text-embedding-3-small (1536 native) must be called with dimensions=768.
# GCP's text-embedding-005 outputs 768 natively — no reduction needed.

MODE = os.getenv("MODE", "local")

LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", {
        "local": "ollama/llama3",
        "demo":  "groq/llama-4-scout",
        "prod":  "azure/gpt-4o",
    }.get(MODE, "ollama/llama3")),

    # Note: Groq has no embedding API — Ollama serves embeddings for both local and demo.
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
    "fallbacks": ["ollama/llama3"] if MODE != "local" else [],
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

FEATURES = {
    "reranker_enabled": MODE == "prod",
    "otel_enabled": True,
    "azure_monitor": MODE == "prod",
}