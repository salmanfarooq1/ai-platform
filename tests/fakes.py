"""Fake adapters for the ports. Tests never reach a real provider.

Embeddings: each lower-cased word is hashed into one of 768 buckets, bucket counts
are summed and the vector is L2-normalised. Same text gives the same vector, and
texts that share words have a higher cosine similarity. `FakeEmbeddings` is an `EmbeddingPort`.

LLM: `FakeLLM` is an `LLMPort` and a `ChatModelPort` in one object. Behind both, `FakeLLM.acompletion` answers
from the context it is given (citing the first chunk), plays the agent's tool-calling turn, and answers the
verifier. Every call is recorded in `FakeLLM.calls`. A test that needs another behaviour subclasses `FakeLLM`,
overrides `acompletion`, and installs it with `fake_llm.use(other)`.

`FakeKnowledgeStore`, `FakeCache` and `FakeS3Client` are in-memory stand-ins that pass the same contract suites
(tests/contracts/) as the real adapters.
"""
import json
import math
import re
import time
import zlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import litellm
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

import config
from core.settings import get_settings
from ports import (
    ChunkRow,
    Completion,
    DocumentRecord,
    EmbeddingDimensionMismatch,
    Embeddings,
    SemanticHit,
)

EMBEDDING_DIM = 768
_WORD = re.compile(r"[a-z0-9]+")


def fake_embedding(text: str) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    for word in _WORD.findall(text.lower()):
        vec[zlib.crc32(word.encode()) % EMBEDDING_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        vec[0] = 1.0
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class FakeEmbeddings:
    """An `EmbeddingPort`. Records every input batch. The model name defaults to the configured embedding model,
    so rows it embeds are never stale against the migration backfill."""

    def __init__(self, model: str | None = None, dim: int = EMBEDDING_DIM, produce_width: int | None = None) -> None:
        """`produce_width` makes the fake emit vectors of another width than `dim`, to test the dimension check."""
        self._model = model or str(get_settings().embed_model)
        self._dim = dim
        self._width = produce_width or dim
        self.calls: list[list[str]] = []

    @property
    def active_model(self) -> str:
        return self._model

    @property
    def active_dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> Embeddings:
        self.calls.append(list(texts))
        vectors = [(fake_embedding(t) * 5)[: self._width] if self._width != self._dim else fake_embedding(t) for t in texts]
        if any(len(v) != self._dim for v in vectors):
            raise EmbeddingDimensionMismatch(f"the fake produced {self._width}-wide vectors, the active dimension is {self._dim}")
        return Embeddings(vectors=vectors, model=self._model, dim=self._dim)


_CHUNK_RE = re.compile(r"\[chunk_(\d+)\] \(from ([^,]+), score [0-9.]+\):\n(.*?)(?=\n\n\[chunk_|\n\nQuestion:)", re.S)


class FakeLLM:
    """An `LLMPort` and a `ChatModelPort`. `acompletion` is the litellm-shaped behaviour behind both."""

    def __init__(self, agent_namespace: str = "default") -> None:
        self.calls: list[dict[str, Any]] = []
        self.agent_namespace = agent_namespace
        self._target: FakeLLM = self

    def use(self, other: "FakeLLM") -> None:
        """Route every call of this fake to `other.acompletion` (a subclass with another behaviour)."""
        self._target = other

    # --- LLMPort ---

    async def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        max_tokens: int,
        temperature: float | None = None,
        response_format: Any = None,
    ) -> Completion:
        kwargs: dict[str, Any] = {"max_tokens": max_tokens}
        if response_format is not None:
            kwargs["response_format"] = response_format
        response = await self._target.acompletion(model=model, messages=[dict(m) for m in messages], **kwargs)
        choice = response.choices[0]
        tokens_in, tokens_out = response.usage.prompt_tokens, response.usage.completion_tokens
        rates = config.MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
        return Completion(
            text=choice.message.content or "", model=model, tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=(tokens_in / 1_000_000) * rates["input"] + (tokens_out / 1_000_000) * rates["output"],
            finish_reason=choice.finish_reason,
        )

    # --- ChatModelPort ---

    def chat_model(self, *, max_tokens: int, temperature: float = 0.0) -> "FakeChatModel":
        return FakeChatModel(self, max_tokens, ())

    def cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        return 0.0

    @property
    def kinds(self) -> list[str]:
        return [c["kind"] for c in self.calls]

    async def acompletion(self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        first = str(messages[0].get("content") or "")
        if kwargs.get("response_format") is not None:
            kind = "synthesis"
            message = {"role": "assistant", "content": self._synthesize(first)}
            finish = "stop"
        elif "compliance answer verifier" in first:
            kind = "verifier"
            message = {"role": "assistant", "content": json.dumps({"supported": True, "notes": "Grounded in the chunks."})}
            finish = "stop"
        elif kwargs.get("tools"):
            if any(m.get("role") == "tool" for m in messages):
                kind = "agent_final"
                message = {"role": "assistant", "content": "Enough context retrieved."}
                finish = "stop"
            else:
                kind = "agent_tool_call"
                question = next(str(m["content"]) for m in messages if m.get("role") == "user")
                args = {"query": question, "namespace": self.agent_namespace, "top_k": 3}
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_fake_1",
                        "type": "function",
                        "function": {"name": "retrieve_chunks", "arguments": json.dumps(args)},
                    }],
                }
                finish = "tool_calls"
        else:
            kind = "other"
            message = {"role": "assistant", "content": "ok"}
            finish = "stop"

        self.calls.append({"kind": kind, "model": model, "messages": messages, "kwargs": kwargs})
        words = sum(len(str(m.get("content") or "").split()) for m in messages)
        return litellm.ModelResponse(
            model=model,
            choices=[{"index": 0, "finish_reason": finish, "message": message}],
            usage={"prompt_tokens": words, "completion_tokens": 7, "total_tokens": words + 7},
        )

    @staticmethod
    def _synthesize(prompt: str) -> str:
        chunks = _CHUNK_RE.findall(prompt)
        if not chunks:
            return json.dumps({"answer": "No context provided.", "confidence": 0.1, "citations": []})
        index, filename, text = chunks[0]
        answer = f"According to {filename.strip()}: {text.strip()[:120]}"
        return json.dumps({
            "answer": answer,
            "confidence": 0.9,
            "citations": [{
                "document_id": "ignored", "source_filename": "ignored",
                "chunk_index": int(index), "relevance_score": 0.0, "excerpt": "",
            }],
        })


class FakeChatModel:
    """What `FakeLLM.chat_model()` returns: LangChain messages in, an AIMessage out, via `FakeLLM.acompletion`."""

    def __init__(self, llm: FakeLLM, max_tokens: int, tools: Sequence[BaseTool]) -> None:
        self._llm, self._max_tokens, self._tools = llm, max_tokens, tuple(tools)

    def bind_tools(self, tools: Sequence[BaseTool]) -> "FakeChatModel":
        return FakeChatModel(self._llm, self._max_tokens, tools)

    @staticmethod
    def _to_dict(message: BaseMessage) -> dict[str, Any]:
        if isinstance(message, SystemMessage):
            return {"role": "system", "content": message.content}
        if isinstance(message, HumanMessage):
            return {"role": "user", "content": message.content}
        if isinstance(message, ToolMessage):
            return {"role": "tool", "content": message.content, "tool_call_id": message.tool_call_id}
        return {"role": "assistant", "content": message.content}

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        kwargs: dict[str, Any] = {"max_tokens": self._max_tokens}
        if self._tools:
            kwargs["tools"] = [{"type": "function", "function": {"name": t.name}} for t in self._tools]
        model = str(get_settings().llm_model)
        response = await self._llm._target.acompletion(
            model=model, messages=[self._to_dict(m) for m in messages], **kwargs)
        message = response.choices[0].message
        raw_calls = getattr(message, "tool_calls", None) or []

        def parts(call: Any) -> dict[str, Any]:
            if isinstance(call, dict):
                return {"name": call["function"]["name"], "args": json.loads(call["function"]["arguments"]), "id": call["id"]}
            return {"name": call.function.name, "args": json.loads(call.function.arguments), "id": call.id}

        return AIMessage(
            content=message.content or "",
            tool_calls=[parts(c) for c in raw_calls],
            response_metadata={
                "model": model,
                "token_usage": {
                    "prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens,
                },
            },
        )


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to reach a provider or the internet."""


def blocked(name: str) -> Any:
    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise NetworkBlockedError(f"Test tried to call real network function litellm.{name}. Use the fakes in tests/fakes.py.")

    return _raise


class _AsyncNull:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> None:
        return None


class FakeConnection:
    """Stands in for an asyncpg connection inside `tenant_connection` (unit tests, no database).

    Every statement is recorded in `queries` as (sql, args). `fetch` returns `rows`, `fetchval` returns
    `scalar`. The first recorded statement of a tenant connection is the `set_config` for the tenant.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = 1) -> None:
        self.rows = rows or []
        self.scalar = scalar
        self.queries: list[tuple[str, tuple[Any, ...]]] = []

    def transaction(self) -> _AsyncNull:
        return _AsyncNull()

    async def execute(self, sql: str, *args: Any) -> str:
        self.queries.append((sql, args))
        return "OK"

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.queries.append((sql, args))
        return self.rows

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.queries.append((sql, args))
        return self.scalar

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        self.queries.append((sql, args))
        return self.rows[0] if self.rows else None


class FakePool:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = 1) -> None:
        self.conn = FakeConnection(rows, scalar)

    def acquire(self) -> Any:
        conn = self.conn

        class _Acquire:
            async def __aenter__(self_inner) -> FakeConnection:
                return conn

            async def __aexit__(self_inner, *exc: Any) -> None:
                return None

        return _Acquire()


# ----------------------------------------------------------------------------------------------- knowledge store

_TOKEN = re.compile(r"[a-z0-9]+")
_BM25_OR_THRESHOLD = 5  # the Postgres adapter switches AND to OR at 5 words; the fake mirrors it


class FakeKnowledgeStore:
    """An in-memory `KnowledgeStore`. Seed knowledge bases with `kbs[tenant_id] = {slug: description}`.

    `fail_with` makes every call raise, for error-path tests. BM25 is word overlap: all query words for a short
    query, any of them from five words up (as in the Postgres adapter).
    """

    def __init__(self, kbs: dict[UUID, dict[str, str]] | None = None, fail_with: Exception | None = None) -> None:
        self.kbs: dict[UUID, dict[str, str]] = kbs or {}
        self.fail_with = fail_with
        self._chunks: list[dict[str, Any]] = []
        self._registry: dict[tuple[UUID, str, str], DocumentRecord] = {}
        self._next_id = 1

    def _check(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def kb_exists(self, tenant_id: UUID, slug: str) -> bool:
        self._check()
        return slug in self.kbs.get(tenant_id, {})

    async def list_knowledge_bases(self, tenant_id: UUID) -> dict[str, str]:
        self._check()
        return dict(sorted(self.kbs.get(tenant_id, {}).items()))

    def _rows(self, tenant_id: UUID, namespace: str) -> list[dict[str, Any]]:
        return [r for r in self._chunks if r["tenant_id"] == tenant_id and r["namespace"] == namespace]

    @staticmethod
    def _hit(row: dict[str, Any], score_key: str, score: float) -> dict[str, Any]:
        meta = dict(row["metadata"])
        return {"id": row["id"], "document_id": row["document_id"], "content": row["content"], "metadata": meta,
                score_key: score, "source_filename": meta.get("source_filename")}

    async def search_bm25(
        self, tenant_id: UUID, query: str, namespace: str, limit: int, *, embedding_model: str, embedding_dim: int,
    ) -> list[dict[str, Any]]:
        self._check()
        words = set(_TOKEN.findall(query.lower()))
        if not words:
            return []
        need_all = len(query.split()) < _BM25_OR_THRESHOLD
        scored = []
        for row in self._rows(tenant_id, namespace):
            if row["embedding_model"] != embedding_model or row["embedding_dim"] != embedding_dim:
                continue
            overlap = len(words & set(_TOKEN.findall(row["content"].lower())))
            if overlap and (overlap == len(words) or not need_all):
                scored.append((overlap / len(words), row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [self._hit(row, "bm25_score", score) for score, row in scored[:limit]]

    async def search_vector(
        self, tenant_id: UUID, embedding: list[float], namespace: str, limit: int,
        *, embedding_model: str, embedding_dim: int, min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        self._check()
        scored = [
            (cosine(embedding, row["embedding"]), row) for row in self._rows(tenant_id, namespace)
            if row["embedding_model"] == embedding_model and row["embedding_dim"] == embedding_dim
        ]
        scored = [(score, row) for score, row in scored if score > min_score]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [self._hit(row, "vector_score", score) for score, row in scored[:limit]]

    async def insert_chunks(
        self, tenant_id: UUID, document_id: str, namespace: str, chunks: Sequence[ChunkRow],
        *, embedding_model: str, embedding_dim: int,
    ) -> None:
        self._check()
        for chunk in chunks:
            self._chunks.append({
                "id": self._next_id, "tenant_id": tenant_id, "document_id": document_id, "namespace": namespace,
                "content": chunk.content, "embedding": list(chunk.embedding), "metadata": dict(chunk.metadata),
                "embedding_model": embedding_model, "embedding_dim": embedding_dim,
            })
            self._next_id += 1

    async def delete_document(self, tenant_id: UUID, document_id: str, namespace: str) -> int:
        self._check()
        keep = [r for r in self._chunks if not (
            r["tenant_id"] == tenant_id and r["document_id"] == document_id and r["namespace"] == namespace)]
        deleted = len(self._chunks) - len(keep)
        self._chunks = keep
        return deleted

    async def document_status(self, tenant_id: UUID, document_id: str, namespace: str, content_hash: str) -> str:
        self._check()
        record = self._registry.get((tenant_id, namespace, document_id))
        if record is None:
            return "new"
        return "unchanged" if record.content_hash == content_hash else "updated"

    async def register_document(
        self, tenant_id: UUID, document_id: str, namespace: str, content_hash: str, chunk_count: int,
        source_filename: str,
    ) -> None:
        self._check()
        self._registry[(tenant_id, namespace, document_id)] = DocumentRecord(
            document_id=document_id, namespace=namespace, source_filename=source_filename, content_hash=content_hash,
            chunk_count=chunk_count, last_ingested_at=datetime.now(timezone.utc),
        )

    async def list_documents(
        self, tenant_id: UUID, namespace: str | None, visible_kbs: Sequence[str] | None,
    ) -> list[DocumentRecord]:
        self._check()
        rows = [
            r for (t, ns, _), r in self._registry.items()
            if t == tenant_id and (namespace is None or ns == namespace) and (visible_kbs is None or ns in visible_kbs)
        ]
        return sorted(rows, key=lambda r: r.last_ingested_at, reverse=True)

    async def count_stale_vectors(self, embedding_model: str, embedding_dim: int) -> int:
        self._check()
        return sum(1 for r in self._chunks
                   if r["embedding_model"] != embedding_model or r["embedding_dim"] != embedding_dim)


# ----------------------------------------------------------------------------------------------- cache

class FakeCache:
    """An in-memory `CachePort`. `data` holds string values and `ttl` the TTL last set for each key.

    `fail_with` makes every call raise `CacheUnavailable` (Redis down). The semantic lookup is a cosine
    scan over the entries, with the same filters as the RediSearch query.
    """

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.fail_with = fail_with
        self.semantic: list[dict[str, Any]] = []
        self.closed = False

    def _check(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def get(self, key: str) -> str | None:
        self._check()
        return self.data.get(key)

    async def set(self, key: str, value: str, *, ttl: int) -> None:
        self._check()
        self.data[key] = value
        self.ttl[key] = ttl

    async def incr(self, key: str, amount: int = 1, *, ttl: int | None = None) -> int:
        self._check()
        total = int(self.data.get(key, "0")) + amount
        self.data[key] = str(total)
        if ttl is not None and total == amount:
            self.ttl[key] = ttl
        return total

    async def expire(self, key: str, ttl: int) -> None:
        self._check()
        if key in self.data:
            self.ttl[key] = ttl

    async def delete(self, key: str) -> None:
        self._check()
        self.data.pop(key, None)
        self.ttl.pop(key, None)

    async def ping(self) -> None:
        self._check()

    async def ensure_semantic_index(self) -> None:
        self._check()

    async def semantic_lookup(
        self, tenant_id: UUID | str, namespace: str, embedding: list[float], *, embedding_model: str,
        retrieval_mode: str, rerank: bool, top_k: int, min_similarity: float,
    ) -> SemanticHit | None:
        self._check()
        best: tuple[float, dict[str, Any]] | None = None
        for entry in self.semantic:
            if (entry["tenant_id"], entry["namespace"], entry["embedding_model"], entry["retrieval_mode"],
                    entry["rerank"], entry["top_k"]) != (str(tenant_id), namespace, embedding_model, retrieval_mode,
                                                         rerank, top_k):
                continue
            similarity = cosine(embedding, entry["embedding"])
            if best is None or similarity > best[0]:
                best = (similarity, entry)
        if best is None or best[0] < min_similarity:
            return None
        return SemanticHit(response=best[1]["response"], similarity=best[0], query=best[1]["query"])

    async def semantic_store(
        self, tenant_id: UUID | str, namespace: str, embedding: list[float], response: str, *, query: str,
        embedding_model: str, retrieval_mode: str, rerank: bool, top_k: int, ttl: int,
    ) -> None:
        self._check()
        self.semantic.append({
            "tenant_id": str(tenant_id), "namespace": namespace, "embedding": list(embedding), "response": response,
            "query": query, "embedding_model": embedding_model, "retrieval_mode": retrieval_mode, "rerank": rerank,
            "top_k": top_k, "expires": time.time() + ttl,
        })

    async def close(self) -> None:
        self.closed = True


# ----------------------------------------------------------------------------------------------- events

class FakeEventBus:
    """A bare `EventBus` that records what is published and delivers to subscribers in order."""

    def __init__(self) -> None:
        self.published: list[Any] = []
        self._handlers: dict[str, list[Any]] = {}

    def subscribe(self, type: str, handler: Any) -> None:
        self._handlers.setdefault(type, []).append(handler)

    async def publish(self, event: Any, *, tx: Any = None) -> None:
        self.published.append(event)
        for handler in [*self._handlers.get(event.type, []), *self._handlers.get("*", [])]:
            try:
                await handler(event, tx)
            except Exception:
                pass  # same contract as the in-process bus: a failing handler does not fail the publisher


# ----------------------------------------------------------------------------------------------- object store

class FakeS3Client:
    """The few boto3 S3 calls `S3ObjectStore` makes, over a dict. Raises botocore's ClientError for a missing key."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls = 0

    @staticmethod
    def _missing(operation: str) -> Exception:
        from botocore.exceptions import ClientError

        return ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, operation)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> dict[str, Any]:
        self.put_calls += 1
        self.objects[(Bucket, Key)] = bytes(Body)
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise self._missing("HeadObject")
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise self._missing("GetObject")
        data = self.objects[(Bucket, Key)]

        class _Body:
            def read(self_inner) -> bytes:
                return data

        return {"Body": _Body()}
