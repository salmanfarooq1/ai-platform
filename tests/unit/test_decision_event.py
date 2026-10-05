"""The `platform.gateway.decision.v1` event: the decision id and verdict, never input text."""
import json
from uuid import uuid4

import pytest

from gateway import Action, ActionKind, Decision
from gateway.record import decision_event
from tests.gateway_helpers import make_ctx

pytestmark = pytest.mark.unit


def test_the_payload_is_the_verdict_and_ids_only():
    ctx = make_ctx()
    ctx.execution_id = uuid4()
    action = Action(ActionKind.KB_READ, "legal", input_text="the secret merger terms", rate=True)
    decision = Decision(allowed=False, stage="policy", reason="kb_not_allowed", policy_version=3)
    decision_id, tenant = uuid4(), ctx.principal.tenant_id

    event = decision_event(decision_id, tenant, ctx, action, decision)

    assert event.type == "platform.gateway.decision.v1" and event.source == "/gateway"
    assert event.subject == str(decision_id) and event.tenantid == str(tenant)
    assert event.data == {
        "decision_id": str(decision_id), "outcome": "deny", "stage": "policy", "reason": "kb_not_allowed",
        "action": "kb.read", "resource": "legal", "request_id": "req-test", "execution_id": str(ctx.execution_id),
    }
    wire = json.dumps(event.to_dict())
    assert "secret merger" not in wire and action.input_hash not in wire  # neither the text nor its hash


def test_a_decision_outside_any_run_has_a_null_execution_id_and_an_allow_says_allow():
    ctx = make_ctx()
    event = decision_event(uuid4(), ctx.principal.tenant_id, ctx, Action(ActionKind.MODEL_INVOKE, "m"), Decision(True, "allow", "allowed"))
    assert event.data["outcome"] == "allow" and event.data["execution_id"] is None and event.data["resource"] == "m"
