"""The bundle of ports a running app holds. Built once from `Settings` by `adapters/registry.py`."""
from dataclasses import dataclass

from ports.cache import CachePort
from ports.data_access import DataAccess
from ports.embeddings import EmbeddingPort
from ports.events import EventBus
from ports.evidence import DecisionSink, EvidenceLookup
from ports.knowledge import KnowledgeStore
from ports.lineage import LineageEmitter
from ports.llm import ChatModelPort, LLMPort
from ports.objects import ObjectStore
from ports.runtime import AgentRuntime


@dataclass(frozen=True)
class Adapters:
    llm: LLMPort
    chat: ChatModelPort
    embeddings: EmbeddingPort
    knowledge: KnowledgeStore
    cache: CachePort
    objects: ObjectStore
    events: EventBus
    runtime: AgentRuntime
    decisions: DecisionSink
    evidence: EvidenceLookup
    data: DataAccess
    lineage: LineageEmitter
