"""Request and response models of the agent routes (Sprint 007 adds the accepted and run models)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    question: str = Field(description="The compliance question to research")
    namespace: str = Field(default="default", description="Document scope hint for the agent")
    max_iterations: int = Field(default=6, ge=1, le=10, description="Max retrieve_chunks calls before forcing synthesis")
    enable_verifier: bool = Field(default=True, description="Whether to verify the drafted answer against retrieved chunks before returning it")
    max_verify_retries: int = Field(default=1, ge=0, le=3, description="How many times verification can send the query back for more retrieval")


class AgentCitation(BaseModel):
    """Mirrors schemas.py Citation exactly."""
    document_id: str
    source_filename: str
    chunk_index: int
    relevance_score: float
    excerpt: str


class AgentResponse(BaseModel):
    question: str
    answer: str
    confidence: float = 0.0
    citations: list[AgentCitation] = []
    model_used: str = ""
    verified: bool | None = None  # None means the verifier did not run for this query
    verification_notes: str = ""
    reasoning_steps: list[str]
    tool_calls_made: int
    total_time_seconds: float
    total_cost_usd: float = 0.0
    flagged: bool = False  # True when a gateway denial cut the run short: the answer is partial
    flag_reason: str | None = None


# The blueprint calls the finished result `AgentQueryResponse`. It is the same model the route always returned.
AgentQueryResponse = AgentResponse


class AgentAccepted(BaseModel):
    """`202` from `/v1/agent/query` when the run takes longer than the sync wait. Poll `decisions_url`'s run."""
    execution_id: UUID
    job_id: UUID


RunStatusName = Literal["queued", "running", "succeeded", "failed", "stopped"]


class AgentRun(BaseModel):
    execution_id: UUID
    job_id: UUID
    status: RunStatusName
    # `error_code` is set when the run failed or was stopped.
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    # The answer, once the run succeeded. None while it runs and when it failed.
    result: AgentQueryResponse | None
    # Where to read the decisions this run caused (the console reads them by request id).
    decisions_url: str


class AgentRunPage(BaseModel):
    items: list[AgentRun]
    next_cursor: str | None
