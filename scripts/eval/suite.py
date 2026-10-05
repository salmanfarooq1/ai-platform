"""The fixed eval suite for the regression gate (Sprint 008).

A small, fixed corpus and fixed questions run through the platform's own retrieval (`api.services.retriever.retrieve`,
hybrid) and answer generation (`generate_with_routing`), with the fake embeddings, the fake LLM and an in-memory
knowledge store from `tests/fakes.py`. No network, no key, no cost, and the result is the same every run, so a change
in a score means the code changed.

The scores are deterministic DeepEval metrics (`BaseMetric` subclasses, no judge model):
- `retrieval_hit`: the expected source is among the retrieved chunks.
- `answer_fact`: the expected fact is in the answer.
- `citation_ok`: the answer names the expected source.

`run_real.py` is the manual run of the same questions with real providers. It is never run in CI.
"""
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # the repository root, when run as a script
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # nothing leaves the machine

from deepeval.metrics import BaseMetric  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

from api.services.embedding import embed_query  # noqa: E402
from api.services.llm import generate_with_routing  # noqa: E402
from api.services.retriever import RetrieverConfig, retrieve  # noqa: E402
from ports import ChunkRow, EmbeddingPort, KnowledgeStore, LLMPort  # noqa: E402

SUITE = "fixed-12"
TENANT = UUID("00000000-0000-0000-0000-00000000e7a1")
NAMESPACE = "eval"
TOP_K = 3

# One chunk per file. The fact comes first: the fake model quotes the start of the best chunk.
CORPUS: dict[str, str] = {
    "breach.md": "Breach notification: a personal data breach must be reported to the supervisory authority within 72 hours.",
    "retention.md": "Record retention: transaction records must be kept for five years after the account is closed.",
    "kyc.md": "Customer due diligence: verify the identity of every new customer before opening an account.",
    "sar.md": "Suspicious activity reports must be filed within 30 days of the first detection of a suspicious transaction.",
    "consent.md": "Consent: marketing messages need the explicit opt in of the person, recorded with the date and the wording.",
    "access.md": "Data subject access: answer a request for a copy of personal data within one month of receiving it.",
    "transfer.md": "International transfers: personal data may leave the region only with standard contractual clauses in place.",
    "audit.md": "Audit logs must be kept tamper evident and available to the auditor for the whole retention period.",
}


@dataclass(frozen=True)
class Case:
    question: str
    source: str  # the file that holds the answer
    fact: str  # a phrase the answer must contain


CASES: tuple[Case, ...] = (
    Case("how fast must a data breach be reported to the supervisory authority", "breach.md", "within 72 hours"),
    Case("how long must transaction records be kept after the account is closed", "retention.md", "five years"),
    Case("what must be verified before opening an account for a new customer", "kyc.md", "identity of every new customer"),
    Case("when must suspicious activity reports be filed", "sar.md", "within 30 days"),
    Case("what do marketing messages need from the person", "consent.md", "explicit opt in"),
    Case("how quickly must a request for a copy of personal data be answered", "access.md", "within one month"),
    Case("when may personal data leave the region", "transfer.md", "standard contractual clauses"),
    Case("how long must audit logs be kept available to the auditor", "audit.md", "whole retention period"),
    Case("deadline to notify the supervisory authority of a personal data breach", "breach.md", "within 72 hours"),
    Case("records kept five years after account closure", "retention.md", "five years"),
    # Two questions the fake retrieval cannot answer: they share no words with their file. They are in the suite on
    # purpose, so the stored baseline is below 1.0 and a real change in retrieval shows in the score either way.
    Case("which obligation covers telling regulators about leaked customer information quickly", "breach.md", "within 72 hours"),
    Case("how long to hold on to old ledgers", "retention.md", "five years"),
)

METRICS = ("retrieval_hit", "answer_fact", "citation_ok")


class _Binary(BaseMetric):
    """A metric that is 1.0 or 0.0 and needs no model."""

    threshold = 1.0
    async_mode = False

    def __init__(self) -> None:
        self.score = 0.0
        self.success = False
        self.reason = ""

    def check(self, case: LLMTestCase) -> bool:
        raise NotImplementedError

    def measure(self, test_case: LLMTestCase, *args: object, **kwargs: object) -> float:
        self.score = 1.0 if self.check(test_case) else 0.0
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args: object, **kwargs: object) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self) -> str:  # type: ignore[override]
        return type(self).__name__


class RetrievalHit(_Binary):
    def check(self, case: LLMTestCase) -> bool:
        return any(str(case.metadata and case.metadata.get("source")) == c.split(":", 1)[0]
                   for c in (case.retrieval_context or []))


class AnswerFact(_Binary):
    def check(self, case: LLMTestCase) -> bool:
        return bool(case.expected_output) and case.expected_output.lower() in case.actual_output.lower()


class CitationOk(_Binary):
    def check(self, case: LLMTestCase) -> bool:
        source = str((case.metadata or {}).get("source"))
        return case.actual_output.startswith(f"According to {source}:")


async def seed(store: KnowledgeStore, embeddings: EmbeddingPort) -> None:
    """Embed and store the corpus, one chunk per file."""
    texts = list(CORPUS.values())
    result = await embeddings.embed(texts)
    for (name, text), vector in zip(CORPUS.items(), result.vectors):
        await store.insert_chunks(
            TENANT, name, NAMESPACE, [ChunkRow(content=text, embedding=vector, metadata={"source_filename": name})],
            embedding_model=result.model, embedding_dim=result.dim,
        )


async def answer(store: KnowledgeStore, embeddings: EmbeddingPort, llm: LLMPort, case: Case) -> LLMTestCase:
    """One question through the platform's retrieval and generation, as a DeepEval test case."""
    query_embedding = await embed_query(embeddings, case.question)
    chunks = await retrieve(
        store=store, query=case.question, query_embedding=query_embedding, namespace=NAMESPACE,
        cfg=RetrieverConfig(top_k=TOP_K, mode="hybrid", rerank=False), tenant_id=TENANT,
    )
    prepared = [{"document_id": c["document_id"], "source_filename": c.get("source_filename") or "unknown", "text": c["content"],
                 "score": c.get("rrf_score", c.get("vector_score", c.get("bm25_score", 0.0)))} for c in chunks]
    if not prepared:
        return LLMTestCase(input=case.question, actual_output="", expected_output=case.fact, retrieval_context=[],
                           metadata={"source": case.source})
    generated, _ = await generate_with_routing(llm, case.question, prepared)
    return LLMTestCase(
        input=case.question, actual_output=generated.answer, expected_output=case.fact,
        retrieval_context=[f"{c['source_filename']}: {c['text']}" for c in prepared], metadata={"source": case.source},
    )


def score(test_cases: list[LLMTestCase]) -> dict[str, float]:
    """The mean of each metric over the cases, rounded to 4 places."""
    metrics = {"retrieval_hit": RetrievalHit(), "answer_fact": AnswerFact(), "citation_ok": CitationOk()}
    return {
        name: round(sum(metric.measure(tc) for tc in test_cases) / len(test_cases), 4) for name, metric in metrics.items()
    }


async def run_suite(store: KnowledgeStore, embeddings: EmbeddingPort, llm: LLMPort) -> dict[str, float]:
    await seed(store, embeddings)
    cases = [await answer(store, embeddings, llm, case) for case in CASES]
    return score(cases)


async def run_fake() -> dict[str, float]:
    """The CI run: the fakes behind the same ports the platform uses."""
    from tests.fakes import FakeEmbeddings, FakeKnowledgeStore, FakeLLM

    store = FakeKnowledgeStore(kbs={TENANT: {NAMESPACE: "fixed eval corpus"}})
    return await run_suite(store, FakeEmbeddings(), FakeLLM())


if __name__ == "__main__":
    print(asyncio.run(run_fake()))
