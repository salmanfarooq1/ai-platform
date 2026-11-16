from unittest.mock import Mock, call

import pytest

from gateway.admin import PolicyConflict
from gateway.policy import DEFAULT_POLICY
from scripts.showcase import m0


@pytest.mark.parametrize("version", [0, 7])
def test_publication_chains_expected_versions(monkeypatch, version):
    baseline = DEFAULT_POLICY.model_dump(mode="json")
    current = {"version": version, "document": baseline} if version else None
    monkeypatch.setattr(m0, "show_policy", Mock(return_value=current))
    publish = Mock(side_effect=[version + 1, version + 2])
    monkeypatch.setattr(m0, "set_policy", publish)
    conn = object()
    document, journey, kb = m0.publish_journey_policy(conn, "fixture", ["legal"], "ollama/chat")
    assert document == baseline and journey == version + 2 and kb == "legal"
    assert publish.call_args_list == [
        call(conn, "fixture", baseline, "showcase-baseline", expected_version=version),
        call(conn, "fixture", {**baseline, "allowed_models": [entry.alias for entry in m0.load_models_lock()
                                                               if entry.alias != "ollama/chat"]},
             "showcase-deny", expected_version=version + 1),
    ]


@pytest.mark.parametrize("conflict_at", [0, 1])
def test_concurrent_publication_stops_on_conflict(monkeypatch, conflict_at):
    baseline = DEFAULT_POLICY.model_dump(mode="json")
    monkeypatch.setattr(m0, "show_policy", Mock(return_value={"version": 7, "document": baseline}))
    publish = Mock(side_effect=([8] if conflict_at else []) + [PolicyConflict("concurrent change")])
    monkeypatch.setattr(m0, "set_policy", publish)
    with pytest.raises(PolicyConflict):
        m0.publish_journey_policy(object(), "fixture", ["legal"], "ollama/chat")
    assert publish.call_count == conflict_at + 1
    assert all("expected_version" in entry.kwargs for entry in publish.call_args_list)


def test_publication_conflict_fails_journey_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(m0, "prerequisites", lambda: ({}, {}, None))
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "placeholder")
    monkeypatch.setattr(m0, "verified_fixture", Mock(side_effect=PolicyConflict("CONFLICTSENTINEL")))
    restore = Mock()
    monkeypatch.setattr(m0, "restore_policy", restore)
    assert m0.main() == 1
    output = capsys.readouterr().out
    assert "FAIL journey: policy head changed (PolicyConflict)" in output
    assert "CONFLICTSENTINEL" not in output
    restore.assert_not_called()
