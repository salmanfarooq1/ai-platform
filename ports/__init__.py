"""Ports: the typed contracts between the platform and every external provider (strict rule 12).

Protocols and frozen dataclasses only. No provider SDK is imported here; adapters implement the ports.
"""
from ports.bundle import Adapters
from ports.cache import CachePort, CacheUnavailable, SemanticHit
from ports.embeddings import EmbeddingDimensionMismatch, EmbeddingError, EmbeddingPort, Embeddings
from ports.events import (
    DECISION_RECORDED,
    DECISIONS_PURGED,
    EVENT_CATALOGUE,
    INGEST_COMPLETED,
    CloudEvent,
    EventBus,
    EventInfo,
    Handler,
)
from ports.knowledge import ChunkRow, DocumentRecord, Hit, KnowledgeStore
from ports.llm import ChatModel, ChatModelPort, Completion, LLMPort
from ports.objects import ObjectNotFound, ObjectStore
from ports.runtime import (
    AgentRuntime,
    RunHandle,
    Runner,
    RunNotFound,
    RunResult,
    RunSpec,
    RunState,
    RunStatus,
)
from ports.sandbox import (
    EgressRule,
    SandboxDriver,
    SandboxEvent,
    SandboxEventKind,
    SandboxExit,
    SandboxLaunch,
    SandboxLimits,
    SandboxMessage,
    SandboxOutput,
    SandboxPolicy,
    SandboxUnavailable,
)

__all__ = [
    "Adapters", "AgentRuntime", "CachePort", "CacheUnavailable", "ChatModel", "ChatModelPort", "ChunkRow", "CloudEvent",
    "Completion", "DECISION_RECORDED", "DECISIONS_PURGED", "DocumentRecord", "EVENT_CATALOGUE", "EventInfo", "INGEST_COMPLETED", "EmbeddingDimensionMismatch", "EmbeddingError",
    "EmbeddingPort", "Embeddings", "EventBus", "Handler", "Hit", "KnowledgeStore", "LLMPort", "ObjectNotFound",
    "ObjectStore", "RunHandle", "RunNotFound", "RunResult", "RunSpec", "RunState", "RunStatus", "Runner", "SemanticHit",
    "EgressRule", "SandboxDriver", "SandboxEvent", "SandboxEventKind", "SandboxExit", "SandboxLaunch", "SandboxLimits",
    "SandboxMessage", "SandboxOutput", "SandboxPolicy", "SandboxUnavailable",
]
