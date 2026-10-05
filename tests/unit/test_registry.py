"""The composition root: one adapter per port from Settings, with overrides for tests, and the settings behind it."""
import pytest

from adapters.inprocess_events import InProcessEventBus
from adapters.inprocess_runtime import InProcessAgentRuntime
from adapters.litellm_chat import LitellmChat
from adapters.litellm_embeddings import LitellmEmbeddings
from adapters.litellm_llm import LitellmLLM
from adapters.local_object_store import LocalObjectStore
from adapters.pg_knowledge import PgKnowledgeStore
from adapters.redis_cache import RedisCache
from adapters.registry import PORT_NAMES, build_adapters
from adapters.s3_object_store import S3ObjectStore
from core.settings import Settings, SettingsError
from tests.fakes import FakeCache, FakeEmbeddings, FakeKnowledgeStore, FakeLLM

pytestmark = pytest.mark.unit


def settings(**env):
    return Settings(mode="local", **env)


def test_the_default_bundle_has_the_real_adapter_for_every_port(tmp_path):
    adapters = build_adapters(settings(object_store_dir=str(tmp_path)), pool=object())
    assert isinstance(adapters.llm, LitellmLLM) and isinstance(adapters.chat, LitellmChat)
    assert isinstance(adapters.embeddings, LitellmEmbeddings) and isinstance(adapters.knowledge, PgKnowledgeStore)
    assert isinstance(adapters.cache, RedisCache) and isinstance(adapters.objects, LocalObjectStore)
    assert isinstance(adapters.events, InProcessEventBus) and isinstance(adapters.runtime, InProcessAgentRuntime)


def test_the_providers_come_from_settings_not_from_the_call_sites():
    adapters = build_adapters(settings(embed_model="m/embed", embedding_dim=512, embed_fallback_models="m/a, m/b ,,"), pool=object())
    assert (adapters.embeddings.active_model, adapters.embeddings.active_dim) == ("m/embed", 512)
    assert adapters.embeddings._fallbacks == ["m/a", "m/b"]  # ordered, blanks dropped


def test_an_override_replaces_one_port_and_the_real_one_is_never_built():
    fake_llm, store, cache = FakeLLM(), FakeKnowledgeStore(), FakeCache()
    adapters = build_adapters(settings(), overrides={"llm": fake_llm, "chat": fake_llm, "knowledge": store, "cache": cache,
                                                      "embeddings": FakeEmbeddings()})  # no pool needed: knowledge is faked
    assert adapters.llm is fake_llm and adapters.chat is fake_llm and adapters.knowledge is store and adapters.cache is cache
    assert isinstance(adapters.events, InProcessEventBus)  # the rest stay real


def test_the_postgres_knowledge_store_needs_a_pool():
    with pytest.raises(ValueError, match="needs a pool"):
        build_adapters(settings())


def test_an_unknown_override_is_refused_so_a_typo_cannot_silently_keep_the_real_adapter():
    with pytest.raises(ValueError, match="unknown adapter override.*lm"):
        build_adapters(settings(), pool=object(), overrides={"lm": object()})


def test_the_port_names_match_the_bundle_fields():
    from dataclasses import fields

    from ports import Adapters

    assert set(PORT_NAMES) == {f.name for f in fields(Adapters)}


def test_the_s3_object_store_is_selected_by_settings():
    adapters = build_adapters(settings(
        object_store="s3", s3_endpoint_url="http://127.0.0.1:9", s3_bucket="b", s3_access_key_id="id",
        s3_secret_access_key="secret",
    ), pool=object(), overrides={"cache": FakeCache()})
    assert isinstance(adapters.objects, S3ObjectStore)


def test_object_store_s3_needs_its_settings_at_startup_and_names_only_the_variables():
    with pytest.raises(ValueError) as err:
        Settings(mode="local", object_store="s3", s3_bucket="b")
    text = str(err.value)
    assert "S3_ENDPOINT_URL" in text and "S3_ACCESS_KEY_ID" in text and "S3_SECRET_ACCESS_KEY" in text


def test_an_unknown_object_store_is_refused():
    with pytest.raises(ValueError):
        Settings(mode="local", object_store="ftp")


def test_get_settings_error_for_s3_names_no_secret(monkeypatch):
    from core.settings import get_settings

    monkeypatch.setenv("OBJECT_STORE", "s3")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "do-not-print-me")
    get_settings.cache_clear()
    try:
        with pytest.raises(SettingsError) as err:
            get_settings()
        assert "do-not-print-me" not in str(err.value) and "S3_BUCKET" in str(err.value)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
