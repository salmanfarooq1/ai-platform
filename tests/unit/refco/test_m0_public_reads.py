from contextlib import nullcontext
from unittest.mock import Mock

import httpx
import pytest

from scripts.showcase import m0


def test_fixture_uses_operator_credential_inspection(monkeypatch):
    conn = object()
    monkeypatch.setenv("SHOWCASE_FIXTURE_KEY", "private-token")
    monkeypatch.setattr(m0, "admin_connection", lambda _: nullcontext(conn))
    inspect = Mock(return_value={"tenant_id": "tenant", "tenant_slug": "fixture", "principal_id": "principal"})
    monkeypatch.setattr(m0, "inspect_credential", inspect, raising=False)
    monkeypatch.setattr(m0, "list_kbs", Mock(return_value=[{"slug": "legal"}]), raising=False)
    assert m0.verified_fixture("owner", {"tenant_id": "tenant", "tenant_slug": "fixture"}) == ("fixture", ["legal"])
    inspect.assert_called_once_with(conn, "private-token")


@pytest.mark.parametrize("field", ["tenant_id", "tenant_slug", "knowledge_bases"])
def test_fixture_rejects_mismatch_or_empty_kbs(monkeypatch, field):
    record = {"tenant_id": "tenant", "tenant_slug": "fixture"}
    if field in {"tenant_id", "tenant_slug"}:
        record[field] = "other"
    monkeypatch.setattr(m0, "list_kbs", Mock(return_value=[] if field == "knowledge_bases" else [{"slug": "legal"}]), raising=False)
    monkeypatch.setenv("SHOWCASE_FIXTURE_KEY", "private-token")
    monkeypatch.setattr(m0, "admin_connection", lambda _: nullcontext(object()))
    monkeypatch.setattr(m0, "inspect_credential", Mock(return_value=record), raising=False)
    with pytest.raises(ValueError):
        m0.verified_fixture("owner", {"tenant_id": "tenant", "tenant_slug": "fixture"})


def test_decision_lookup_uses_auditor_and_request_filter():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [
            {"id": "allow", "reason": None}, {"id": "deny", "reason": "model_not_allowed"}], "next_cursor": None})

    with httpx.Client(base_url="http://gateway", transport=httpx.MockTransport(respond)) as client:
        assert m0.recorded_decision(client, {"Authorization": "Bearer auditor"}, "request", "model_not_allowed") == "deny"
    assert requests[0].url.path == "/v1/decisions"
    assert requests[0].url.params["request_id"] == "request"
    assert requests[0].headers["authorization"] == "Bearer auditor"
