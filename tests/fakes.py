"""Deterministic fake LLM and embeddings. Tests never reach a real provider.

Embeddings: each lower-cased word is hashed into one of 768 buckets, bucket counts
are summed and the vector is L2-normalised. Same text gives the same vector, and
texts that share words have a higher cosine similarity.

LLM: `FakeLLM.acompletion` stands in for `litellm.acompletion`. It answers from the
context it is given (citing the first chunk), plays the agent's tool-calling turn,
and answers the verifier. Every call is recorded in `FakeLLM.calls`.
"""
import json
import math
import re
import zlib
from typing import Any

import litellm

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
    """Stands in for `litellm.aembedding`. Records every input batch."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def aembedding(self, *, model: str, input: list[str], **kwargs: Any) -> Any:
        self.calls.append(list(input))
        return litellm.EmbeddingResponse(
            model=model,
            data=[{"object": "embedding", "index": i, "embedding": fake_embedding(t)} for i, t in enumerate(input)],
        )


_CHUNK_RE = re.compile(r"\[chunk_(\d+)\] \(from ([^,]+), score [0-9.]+\):\n(.*?)(?=\n\n\[chunk_|\n\nQuestion:)", re.S)


class FakeLLM:
    """Stands in for `litellm.acompletion`, used directly and through ChatLiteLLM."""

    def __init__(self, agent_namespace: str = "default") -> None:
        self.calls: list[dict[str, Any]] = []
        self.agent_namespace = agent_namespace

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
