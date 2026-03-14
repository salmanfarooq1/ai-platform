from .async_ingest import ingestion_pipeline as http_ingestion_pipeline
from .db_ingest import ingestion_pipeline as db_ingestion_pipeline

__all__ = [
    'http_ingestion_pipeline',
    'db_ingestion_pipeline'
]
