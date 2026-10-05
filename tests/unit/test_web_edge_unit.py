"""Web edge pieces that need no database: the session store, the scope map and the preview setting."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.web_edge.session import (
    ABSOLUTE_CAP,
    KEY_PREFIX,
    SLIDING_TTL,
    create_session,
    csrf_matches,
    delete_session,
    load_session,
    redis_key,
)
from core.identity.models import Scope
from core.settings import Settings, SettingsError, get_settings
from gateway import Action, ActionKind
from gateway.boundary import SCOPE_ACTIONS
from gateway.enforce import STAGES, _decide
from tests.gateway_helpers import make_ctx

pytestmark = pytest.mark.unit


class MemoryRedis:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value
        self.ttl[key] = ex

    async def get(self, key):
        return self.data.get(key)

    async def expire(self, key, seconds):
        self.ttl[key] = seconds

    async def delete(self, key):
        self.data.pop(key, None)


async def test_session_value_has_the_contract_fields_and_no_key_material():
    redis, pid, tid = MemoryRedis(), uuid4(), uuid4()
    cookie, session = await create_session(redis, pid, tid, frozenset({"query", "kb:read"}), preview=False)
    (key,) = redis.data
    assert key == KEY_PREFIX + hashlib.sha256(cookie.encode()).hexdigest()
    assert cookie not in key and len(cookie) >= 43  # 32 random bytes, urlsafe
    stored = json.loads(redis.data[key])
    assert set(stored) == {"principal_id", "tenant_id", "scopes", "csrf", "created_at", "preview", "key_prefix"}
    assert stored["key_prefix"] is None
    assert stored["scopes"] == ["kb:read", "query"] and stored["csrf"] == session.csrf
    assert redis.ttl[key] == int(SLIDING_TTL.total_seconds())


async def test_a_hit_slides_the_ttl_but_never_past_the_absolute_cap():
    redis = MemoryRedis()
    cookie, session = await create_session(redis, uuid4(), uuid4(), frozenset({"query"}), preview=False)
    assert (await load_session(redis, cookie)) == session
    assert redis.ttl[redis_key(cookie)] == int(SLIDING_TTL.total_seconds())
    # a session 23 hours old can live only one more hour
    old = json.loads(redis.data[redis_key(cookie)])
    old["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
    redis.data[redis_key(cookie)] = json.dumps(old)
    assert await load_session(redis, cookie) is not None
    assert 3500 <= redis.ttl[redis_key(cookie)] <= 3600


async def test_a_session_past_the_absolute_cap_is_gone():
    redis = MemoryRedis()
    cookie, _ = await create_session(redis, uuid4(), uuid4(), frozenset({"query"}), preview=False)
    old = json.loads(redis.data[redis_key(cookie)])
    old["created_at"] = (datetime.now(timezone.utc) - ABSOLUTE_CAP - timedelta(seconds=1)).isoformat()
    redis.data[redis_key(cookie)] = json.dumps(old)
    assert await load_session(redis, cookie) is None
    assert redis.data == {}


async def test_unknown_corrupt_and_deleted_sessions_load_as_none():
    redis = MemoryRedis()
    assert await load_session(redis, "nope") is None
    redis.data[redis_key("bad")] = "{not json"
    assert await load_session(redis, "bad") is None
    cookie, _ = await create_session(redis, uuid4(), uuid4(), frozenset(), preview=True)
    await delete_session(redis, cookie)
    assert await load_session(redis, cookie) is None


async def test_csrf_comparison():
    _, session = await create_session(MemoryRedis(), uuid4(), uuid4(), frozenset(), preview=False)
    assert csrf_matches(session, session.csrf)
    assert not csrf_matches(session, None) and not csrf_matches(session, "") and not csrf_matches(session, session.csrf + "x")


def test_audit_read_scope_grants_only_audit_read_and_admin_grants_it_too():
    assert SCOPE_ACTIONS[Scope.AUDIT_READ.value] == frozenset({"audit.read"})
    assert "audit.read" in SCOPE_ACTIONS[Scope.ADMIN.value]
    for scope in ("kb:read", "kb:write", "query", "agent"):
        assert "audit.read" not in SCOPE_ACTIONS[scope]


async def test_a_policy_cannot_narrow_audit_read_by_resource():
    nothing = {"allowed_kbs": [], "allowed_tools": [], "allowed_models": []}
    ctx = make_ctx(scopes=("audit:read",), policy=nothing, version=3)
    for resource in ("decisions", "policies", "principals", "usage"):
        decision = await _decide(ctx, Action(ActionKind.AUDIT_READ, resource=resource), STAGES)
        assert decision.allowed and decision.policy_version == 3


async def test_without_the_scope_audit_read_is_denied_at_the_boundary():
    decision = await _decide(make_ctx(scopes=("kb:read", "query", "agent")), Action(ActionKind.AUDIT_READ, resource="decisions"), STAGES)
    assert (decision.allowed, decision.stage, decision.reason) == (False, "boundary", "action_not_allowed")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for name in ("MODE", "DATABASE_URL", "REDIS_URL", "PREVIEW_PRINCIPAL_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_preview_principal_id_defaults_to_unset_and_blank_means_unset(clean_env):
    assert get_settings().preview_principal_id is None
    get_settings.cache_clear()
    clean_env.setenv("PREVIEW_PRINCIPAL_ID", "  ")
    assert get_settings().preview_principal_id is None


def test_preview_principal_id_must_be_a_uuid(clean_env):
    clean_env.setenv("PREVIEW_PRINCIPAL_ID", "not-a-uuid")
    with pytest.raises(SettingsError, match="PREVIEW_PRINCIPAL_ID"):
        get_settings()


def test_preview_principal_id_is_accepted_in_local_and_public_preview_and_refused_in_prod(clean_env):
    pid = str(uuid4())
    clean_env.setenv("PREVIEW_PRINCIPAL_ID", pid)
    assert str(get_settings().preview_principal_id) == pid
    for mode in ("public-preview", "prod"):
        get_settings.cache_clear()
        clean_env.setenv("MODE", mode)
        clean_env.setenv("DATABASE_URL", "postgresql://u:p@db/x")
        clean_env.setenv("REDIS_URL", "redis://r")
        if mode == "prod":
            with pytest.raises(SettingsError, match="PREVIEW_PRINCIPAL_ID must not be set when MODE=prod"):
                get_settings()
        else:
            assert str(get_settings().preview_principal_id) == pid


def test_settings_class_default_is_none():
    assert Settings.model_fields["preview_principal_id"].default is None
