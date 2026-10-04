"""The network guard (tests/conftest.py) must make any real provider call fail loudly."""
import socket

import litellm
import pytest

from tests.fakes import FakeEmbeddings, FakeLLM, NetworkBlockedError, cosine, fake_embedding

pytestmark = pytest.mark.unit


async def test_guard_blocks_litellm_completion():
    with pytest.raises(NetworkBlockedError, match="litellm.acompletion"):
        await litellm.acompletion(model="gemini/x", messages=[{"role": "user", "content": "hi"}])


async def test_guard_blocks_litellm_embedding():
    with pytest.raises(NetworkBlockedError, match="litellm.aembedding"):
        await litellm.aembedding(model="gemini/x", input=["hi"])


def test_guard_blocks_sync_litellm_entry_points():
    with pytest.raises(NetworkBlockedError):
        litellm.completion(model="gemini/x", messages=[])
    with pytest.raises(NetworkBlockedError):
        litellm.embedding(model="gemini/x", input=["hi"])


def test_guard_blocks_external_socket_connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkBlockedError, match="93.184.216.34"):
            s.connect(("93.184.216.34", 443))
    finally:
        s.close()


def test_guard_blocks_external_dns_lookup():
    with pytest.raises(NetworkBlockedError, match="api.example.test"):
        socket.getaddrinfo("api.example.test", 443)


def test_guard_allows_loopback():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(server.getsockname())
    finally:
        client.close()
        server.close()


# --- the fakes themselves ---

def test_fake_embedding_is_deterministic_and_unit_length():
    a = fake_embedding("GDPR fines are large")
    assert a == fake_embedding("gdpr FINES are large")
    assert len(a) == 768
    assert sum(x * x for x in a) == pytest.approx(1.0)


def test_fake_embedding_shared_words_score_higher():
    base = fake_embedding("data breach notification deadline")
    related = fake_embedding("breach notification rules")
    unrelated = fake_embedding("quarterly marketing budget")
    assert cosine(base, related) > cosine(base, unrelated)
    assert cosine(base, base) == pytest.approx(1.0)


async def test_fake_embeddings_records_calls_through_litellm(monkeypatch):
    fake = FakeEmbeddings()
    monkeypatch.setattr(litellm, "aembedding", fake.aembedding)
    resp = await litellm.aembedding(model="m", input=["a b", "c"])
    assert fake.calls == [["a b", "c"]]
    assert resp.data[0]["embedding"] == fake_embedding("a b")


async def test_fake_llm_answers_from_context_and_records_calls(monkeypatch):
    from api.services.llm import generate_with_citations

    fake = FakeLLM()
    monkeypatch.setattr(litellm, "acompletion", fake.acompletion)
    chunks = [{"document_id": "d1", "source_filename": "a.md", "text": "Alpha beta gamma.", "score": 0.5}]
    answer, usage = await generate_with_citations("what is alpha?", chunks)
    assert answer.answer.startswith("According to a.md: Alpha beta gamma.")
    assert [c.document_id for c in answer.citations] == ["d1"]
    assert fake.kinds == ["synthesis"]
    assert usage["completion_tokens"] == 7
