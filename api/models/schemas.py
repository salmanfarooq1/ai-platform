from pydantic import BaseModel, Field
from typing import Any

# --- Ingest ---

class IngestRequest(BaseModel):
    namespace: str = Field(default="default", description="Scope for this document — isolates tenants or projects")
    document_id: str = Field(description="Unique identifier for this document — filename or UUID")

class IngestResponse(BaseModel):
    document_id: str
    namespace: str
    total_chunks: int
    total_time_seconds: float
    throughput_chunks_per_second: float

# --- Search ---

class SearchRequest(BaseModel):
    query: str = Field(description="Natural language query to search against stored chunks")
    namespace: str = Field(default="default", description="Scope to search within")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of chunks to retrieve")

class SearchResult(BaseModel):
    document_id: str
    namespace: str
    content: str
    score: float
    metadata: dict[str, Any]

class SearchResponse(BaseModel):
    query: str
    answer: str                  # The LLM-generated answer text
    confidence: float            # LLM self-reported confidence (0.0–1.0)
    needs_clarification: bool    # LLM flagged the question as ambiguous
    results: list[SearchResult]  # The supporting chunk citations
    total_results: int

# --- Health ---

class HealthResponse(BaseModel):
    status: str                  # "ok" or "degraded"
    db: str                      # "ok" or "error: <reason>"
    redis: str                   # "ok" or "error: <reason>"
    version: str

class Citation(BaseModel):
    """A reference to the specific chunk from the DB that supported the answer."""
    document_id: str
    source_filename: str
    chunk_index: int
    relevance_score: float
    excerpt: str  # First 100 chars of the chunk for context

class GeneratedAnswer(BaseModel):
    """Every LLM answer MUST be structured. No regex parsing!"""
    answer: str
    citations: list[Citation]
    confidence: float       # e.g., 0.95
    model_used: str
    needs_clarification: bool