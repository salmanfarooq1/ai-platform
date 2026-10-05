"""Sprint 010: the Kafka adapter's pure parts. Topic names, CloudEvents binary mode, the settings, the fake broker's
partitioner and that the composition root keeps the outbox in the request path."""
import logging
from datetime import timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from adapters.kafka_event_bus import KafkaConfig, decode_event, dlq_topic, encode_event, topic_for
from adapters.pg_outbox_events import OutboxEventBus, OutboxRelay
from adapters.registry import build_adapters
from core.settings import Settings
from ports import CloudEvent
from tests.fake_kafka import murmur2, partition_of
from tests.fakes import FakeCache, FakeEmbeddings, FakeKnowledgeStore, FakeLLM

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def sample(**over):
    fields = {"type": "platform.gateway.decision.v1", "source": "/gateway", "subject": "d-1", "tenantid": str(uuid4()),
              "data": {"decision_id": "d-1", "outcome": "allow"}}
    return CloudEvent(**{**fields, **over})


@pytest.mark.parametrize("event_type,topic", [
    ("platform.gateway.decision.v1", "platform.gateway.decision"),
    ("platform.ingest.completed.v1", "platform.ingest.completed"),
    ("platform.gateway.purge.v12", "platform.gateway.purge"),
    ("thing.happened.v1", "platform.thing.happened"),
])
def test_the_topic_is_the_type_without_its_version(event_type, topic):
    assert topic_for(event_type) == topic
    assert dlq_topic(topic) == topic + ".dlq"


def test_an_event_round_trips_through_binary_content_mode():
    ev = sample()
    value, headers = encode_event(ev)
    names = dict(headers)
    assert names["ce_specversion"] == b"1.0" and names["ce_id"] == ev.id.encode() and names["ce_type"] == ev.type.encode()
    assert names["ce_tenantid"] == ev.tenantid.encode() and names["ce_subject"] == b"d-1" and names["content-type"] == b"application/json"
    assert b"decision_id" in value and b"specversion" not in value  # the value is the data only
    assert decode_event(value, headers) == ev
    assert decode_event(value, headers).time.tzinfo is timezone.utc


def test_an_event_without_a_subject_has_no_subject_header():
    value, headers = encode_event(sample(subject=None))
    assert "ce_subject" not in dict(headers) and decode_event(value, headers).subject is None


@pytest.mark.parametrize("break_it", ["drop_id", "bad_version", "bad_json", "not_object"])
def test_a_record_that_is_not_a_cloud_event_is_refused(break_it):
    value, headers = encode_event(sample())
    if break_it == "drop_id":
        headers = tuple(h for h in headers if h[0] != "ce_id")
    elif break_it == "bad_version":
        headers = tuple((n, b"0.3" if n == "ce_specversion" else v) for n, v in headers)
    elif break_it == "bad_json":
        value = b"{not json"
    else:
        value = b"[1, 2]"
    with pytest.raises(ValueError):
        decode_event(value, headers)


def test_the_partitioner_is_murmur2_and_keeps_a_key_on_one_partition():
    # Test vectors from Kafka's own `UtilsTest.testMurmur2` (signed 32-bit there).
    assert murmur2(b"21") == -973932308 & 0xFFFFFFFF
    assert murmur2(b"foobar") == -790332482 & 0xFFFFFFFF
    assert murmur2(b"a-little-bit-long-string") == -985981536 & 0xFFFFFFFF
    keys = [str(uuid4()).encode() for _ in range(50)]
    assert all(0 <= partition_of(k, 3) < 3 for k in keys)
    assert {partition_of(k, 3) for k in keys} == {0, 1, 2}  # spreads over the partitions
    assert all(partition_of(k, 3) == partition_of(k, 3) for k in keys)


def test_kafka_settings_default_to_the_outbox_and_need_a_bootstrap_when_chosen():
    assert Settings(mode="local").event_bus == "outbox"
    with pytest.raises(ValueError, match="KAFKA_BOOTSTRAP"):
        Settings(mode="local", event_bus="kafka")
    ok = Settings(mode="local", event_bus="kafka", kafka_bootstrap="broker:9092")
    assert (ok.kafka_client_id, ok.kafka_group_id, ok.kafka_max_attempts) == ("gap-platform", "gap-platform", 5)


def test_sasl_needs_a_mechanism_a_user_and_a_password_and_the_password_is_masked(caplog):
    with pytest.raises(ValueError, match="KAFKA_SASL_PASSWORD"):
        Settings(mode="local", kafka_security_protocol="SASL_SSL", kafka_sasl_mechanism="PLAIN", kafka_sasl_username="u")
    s = Settings(mode="local", event_bus="kafka", kafka_bootstrap="b:9093", kafka_security_protocol="SASL_SSL",
                 kafka_sasl_mechanism="SCRAM-SHA-512", kafka_sasl_username="svc", kafka_sasl_password="s3cr3t-value")
    cfg = KafkaConfig(bootstrap="b:9093", security_protocol=s.kafka_security_protocol, sasl_mechanism=s.kafka_sasl_mechanism,
                      sasl_username=s.kafka_sasl_username, sasl_password=s.kafka_sasl_password)
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("adapters.kafka").info("config %r settings %r", cfg, s)
    shown = caplog.text + repr(cfg) + repr(s) + str(s.model_dump())
    assert "s3cr3t-value" not in shown
    assert cfg.client_options()["sasl_plain_password"] == "s3cr3t-value"  # the one place it is unwrapped
    assert "ssl_context" in cfg.client_options()


def test_with_kafka_the_request_path_still_writes_the_outbox_and_only_the_relay_reaches_kafka():
    s = Settings(mode="local", event_bus="kafka", kafka_bootstrap="broker:9092")
    adapters = build_adapters(s, pool=object(), overrides={
        "llm": FakeLLM(), "chat": FakeLLM(), "embeddings": FakeEmbeddings(), "knowledge": FakeKnowledgeStore(), "cache": FakeCache(),
    })
    assert isinstance(adapters.events, OutboxEventBus)  # Kafka is never inside the decision transaction
    from workers.context import make_relay

    relay, _ = make_relay(s, object())  # type: ignore[arg-type]
    assert isinstance(relay, OutboxRelay) and type(relay._target).__name__ == "KafkaEventBus"
    out, _ = make_relay(Settings(mode="local"), object())  # type: ignore[arg-type]
    assert type(out._target).__name__ == "InProcessEventBus"


def test_sprint_010_adds_no_migration():
    heads = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads()
    assert heads == ["0010"] or [h.split("_")[0] for h in heads] == ["0010"]


def test_a_bad_kafka_setting_error_names_the_variable_and_not_the_password(monkeypatch):
    from core.settings import SettingsError, get_settings

    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD", "do-not-print-me")
    get_settings.cache_clear()
    try:
        with pytest.raises(SettingsError) as err:
            get_settings()
        assert "do-not-print-me" not in str(err.value) and "KAFKA_SASL_MECHANISM" in str(err.value)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_the_producer_limits_have_short_defaults_and_reach_the_client_options():
    s = Settings(mode="local")
    assert (s.kafka_request_timeout_seconds, s.kafka_send_timeout_seconds) == (10.0, 15.0)
    cfg = KafkaConfig(bootstrap="b:9092", request_timeout_seconds=3)
    assert cfg.client_options()["request_timeout_ms"] == 3000 and cfg.send_timeout_seconds == 15.0
    with pytest.raises(ValueError):
        Settings(mode="local", kafka_send_timeout_seconds=0)
