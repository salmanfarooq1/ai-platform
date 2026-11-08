"""Value ownership for the evidence and data ports."""
from uuid import uuid4

import pytest

from ports import DataResult, DecisionEntry

pytestmark = pytest.mark.unit


def decision_entry(extensions):
    return DecisionEntry(
        tenant_id=uuid4(), principal_id=None, request_id="request", trace_id="trace", action="system.read",
        resource="system/modules", outcome="allow", stage="allow", reason="allowed", policy_version=None,
        input_sha256=None, execution_id=None, extensions=extensions,
    )


def test_decision_entry_takes_a_deep_immutable_copy_of_extensions():
    source = {"one": {"nested": [1, "two"]}}
    entry = decision_entry(source)
    source["one"]["nested"].append("later")
    assert entry.extensions["one"]["nested"] == (1, "two")
    with pytest.raises(TypeError):
        entry.extensions["one"]["new"] = "value"  # type: ignore[index]


def test_decision_entry_rejects_non_json_values_and_non_string_keys():
    with pytest.raises(TypeError, match="JSON object keys"):
        decision_entry({1: "not-json"})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="unsupported JSON value"):
        decision_entry({"bad": object()})


def test_data_result_takes_ownership_of_rows():
    source = {"values": ["before"]}
    result = DataResult(columns=("values",), rows=(source,))
    source["values"].append("after")
    assert result.rows[0]["values"] == ("before",)
