"""Ingest one file from a standalone script: open a pool, build the ports from Settings, ingest, close the pool.

The scripts here used to rely on `ingestion_pipeline` creating its own pool. The pipeline now takes ports
(`adapters/registry.py` builds them), so this helper does what the API lifespan does, once per call.
"""
from adapters.registry import build_adapters
from core.database.pool import create_pool
from core.pipeline.db_ingest import ingestion_pipeline
from core.settings import get_settings


async def standalone_ingest(**kwargs):
    pool = await create_pool()
    try:
        adapters = build_adapters(get_settings(), pool=pool)
        return await ingestion_pipeline(store=adapters.knowledge, embeddings=adapters.embeddings, **kwargs)
    finally:
        await pool.close()
