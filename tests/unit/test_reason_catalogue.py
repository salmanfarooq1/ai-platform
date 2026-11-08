"""Every reason code the gateway, the guardrails and the auth layer can emit has a catalogue entry.

The scan reads the source with `ast`, so a new code added in those files fails here until it is catalogued.
"""
import ast
from pathlib import Path

import pytest

from gateway.policy import PolicyDocument
from gateway.reasons import REASONS, all_reasons
from tests.harness import ROOT

pytestmark = pytest.mark.unit

SCANNED = [*sorted((ROOT / "gateway").glob("*.py")), *sorted((ROOT / "evidence").glob("*.py")), ROOT / "api" / "auth.py", ROOT / "api" / "gateway_deps.py"]


def _text(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def emitted_codes(path: Path) -> set[str]:
    """Reason codes written as literals: `reason=...`, `_deny(ctx, stage, code)`, `deny_all_boundary(_, code)`,
    a `(code, message)` return from the guardrails, and `ALLOW_REASON`."""
    found: set[str] = set()
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "reason" and (value := _text(kw.value)):
                    found.add(value)
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name == "_deny" and len(node.args) > 2 and (value := _text(node.args[2])):
                found.add(value)
            if name == "deny_all_boundary" and len(node.args) > 1 and (value := _text(node.args[1])):
                found.add(value)
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple) and path.name == "guardrails.py":
            if node.value.elts and (value := _text(node.value.elts[0])):
                found.add(value)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ALLOW_REASON" for t in node.targets):
            if value := _text(node.value):
                found.add(value)
    return found


def test_the_scan_finds_the_codes_we_know_about():
    found: set[str] = set()
    for path in SCANNED:
        found |= emitted_codes(path)
    known = {
        "allowed", "no_principal", "missing_scope", "action_not_allowed", "tool_call_limit", "policy_unavailable",
        "kb_not_allowed", "tool_not_allowed", "model_not_allowed", "token_limit", "query_blocked",
        "rate_limit_exceeded", "daily_token_budget_exceeded", "dependency_unavailable", "internal_error",
        "decision_unrecorded",
    }
    assert known <= found, f"the scan no longer sees: {sorted(known - found)}"


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_emitted_reason_code_has_a_catalogue_entry(path):
    missing = sorted(emitted_codes(path) - set(REASONS))
    assert not missing, f"{path.relative_to(ROOT)} emits reason codes with no entry in gateway/reasons.py: {missing}"


def test_every_catalogue_entry_is_complete_and_unique():
    entries = all_reasons()
    assert len({r.code for r in entries}) == len(entries) == len(REASONS)
    for r in entries:
        assert r.title.strip() and r.sentence.strip() and r.stage.strip(), r.code
        assert r.sentence.endswith("."), r.code


def test_every_policy_field_names_a_real_policy_key():
    keys = set(PolicyDocument.model_fields)
    for r in all_reasons():
        assert r.policy_field is None or r.policy_field in keys, r.code


def test_the_catalogue_has_no_code_that_nothing_emits():
    found: set[str] = set()
    for path in SCANNED:
        found |= emitted_codes(path)
    assert set(REASONS) <= found, f"catalogued but never emitted: {sorted(set(REASONS) - found)}"
