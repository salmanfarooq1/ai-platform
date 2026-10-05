"""Small pure pieces of Sprint 007: backoff, the payload rule, the context that travels to a worker, CloudEvent
round trips and the job-to-run-state mapping."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from adapters.job_runtime import state_of
from api.services.run_status import run_status_word
from core.database import jobs
from core.identity.models import Principal
from gateway.boundary import build_boundary
from gateway.context import context_from_payload, context_to_payload
from gateway.policy import PolicyDocument
from gateway.types import EnforcementContext, GatewayRuntime
from ports import CloudEvent, RunState
from tests.gateway_helpers import FakeRedis

pytestmark = pytest.mark.unit


def test_backoff_doubles_with_each_attempt_and_stays_within_its_jitter():
    for attempts in (1, 2, 3, 4):
        for _ in range(50):
            delay = jobs.backoff_seconds(2.0, attempts)
            assert 2.0 * 2 ** attempts * 0.8 <= delay <= 2.0 * 2 ** attempts * 1.2
    assert jobs.backoff_seconds(0.0, 5) == 0.0


def test_a_payload_may_not_hold_a_long_text_anywhere():
    jobs.check_payload({"namespace": "legal", "n": 3, "nested": {"list": ["short"]}})
    for bad in ({"t": "x" * 4097}, {"a": {"b": ["x" * 5000]}}, {"é": "é" * 2100}):
        with pytest.raises(jobs.PayloadTooLarge):
            jobs.check_payload(bad)


def test_the_context_a_worker_rebuilds_is_the_one_the_request_had():
    principal = Principal(id=uuid4(), tenant_id=uuid4(), kind="service", scopes=frozenset({"agent", "kb:read"}))
    boundary = build_boundary(principal, PolicyDocument(allowed_kbs=["legal"], allowed_tools="*", allowed_models=["m/a"], blocked_terms=["Secret"]), 7)
    ctx = EnforcementContext(principal=principal, request_id="r1", trace_id="t" * 32, boundary=boundary,
                             runtime=GatewayRuntime(pool=None, cache=FakeRedis()), execution_id=uuid4())
    payload = context_to_payload(ctx)
    assert "scopes" in payload["principal"] and "api_key" not in str(payload) and "secret" not in str(payload["principal"]).lower()
    rebuilt = context_from_payload(GatewayRuntime(pool=None, cache=FakeRedis()), payload)
    assert rebuilt.principal == principal and rebuilt.boundary == boundary and rebuilt.execution_id == ctx.execution_id
    assert (rebuilt.request_id, rebuilt.trace_id, rebuilt.boundary.policy_version) == ("r1", "t" * 32, 7)
    assert rebuilt.boundary.allows_kb("legal") and not rebuilt.boundary.allows_kb("default")  # nothing widened


def test_a_cloud_event_survives_the_outbox_round_trip():
    ev = CloudEvent(type="platform.test.v1", source="/t", subject="s", tenantid=str(uuid4()), data={"a": 1},
                    time=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert CloudEvent.from_dict(ev.to_dict()) == ev
    assert CloudEvent.from_dict(CloudEvent(type="t", source="/s", subject=None, tenantid="x", data={}).to_dict()).subject is None


@pytest.mark.parametrize("status,code,state,word", [
    ("queued", None, RunState.RUNNING, "queued"), ("running", None, RunState.RUNNING, "running"),
    ("succeeded", None, RunState.SUCCEEDED, "succeeded"), ("failed", "agent_run_failed", RunState.FAILED, "failed"),
    ("failed", "stopped", RunState.STOPPED, "stopped"), ("dead", "lease_expired", RunState.FAILED, "failed"),
])
def test_a_job_maps_to_a_run_state_and_a_console_word(status, code, state, word):
    now = datetime.now(timezone.utc)
    row = jobs.JobRow(
        id=uuid4(), tenant_id=uuid4(), kind="agent_run", status=status, payload={}, idempotency_key=None, attempts=1,
        max_attempts=2, run_after=now, lease_until=None, locked_by=None, progress_done=0, progress_total=0,
        error_code=code, error_detail=None, resource=None, execution_id=uuid4(), result=None, cancel_requested=False,
        created_at=now, updated_at=now, started_at=None, finished_at=None, principal_id=None, namespace=None,
    )
    assert state_of(row) is state and run_status_word(status, code) == word


async def test_l3_the_recursion_limit_warning_never_logs_the_question(caplog):
    import logging

    from langgraph.errors import GraphRecursionError

    from api.agent.runner import make_agent_runner
    from ports import RunSpec

    class Graph:
        async def ainvoke(self, state, config):
            raise GraphRecursionError("limit")

    secret = "what is the salary of the CEO jane-doe-4711"
    ctx = EnforcementContext(principal=None, request_id="r", trace_id="t", boundary=None, runtime=None)  # type: ignore[arg-type]
    spec = RunSpec(kind="agent.query", input={"question": secret, "max_iterations": 1, "max_verify_retries": 0,
                                              "enable_verifier": False}, tenant_id=uuid4(), context=ctx, execution_id=uuid4())
    with caplog.at_level(logging.WARNING, logger="api.agent.runner"):
        out = await make_agent_runner(lambda: Graph())(spec)
    assert out.result is None
    assert caplog.records and "jane-doe-4711" not in caplog.text and str(spec.execution_id) in caplog.text
