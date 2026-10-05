"""The reason-code catalogue: a plain title and sentence for every code the platform can record.

Every `reason` in a `gateway_decisions` row is one of these codes. The console serves this list at
`/v1/reason-codes`, and the UI shows the sentence next to the code. `policy_field` names the key of the tenant
policy document that causes the deny, or is None when no policy key is behind it (a scope, a platform limit
or a fault). A unit test scans the gateway, guardrails and auth code and fails when an emitted code is
missing here.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReasonInfo:
    code: str
    title: str
    sentence: str
    policy_field: str | None
    stage: str


_ENTRIES = (
    ReasonInfo("allowed", "Allowed", "The call passed every check.", None, "allow"),
    ReasonInfo(
        "no_principal", "No identity", "The call had no verified identity, so it was stopped.", None, "principal",
    ),
    ReasonInfo(
        "missing_scope", "Missing scope", "The key does not hold the scope this call needs.", None, "boundary",
    ),
    ReasonInfo(
        "action_not_allowed", "Action not allowed", "The key's scopes do not allow this kind of action.", None, "boundary",
    ),
    ReasonInfo(
        "tool_call_limit", "Tool call limit reached", "The agent used all the tool calls the policy allows for one request.",
        "max_tool_calls", "boundary",
    ),
    ReasonInfo(
        "policy_unavailable", "Policy unavailable",
        "The tenant policy could not be read, so every action is stopped until it can.", None, "policy",
    ),
    ReasonInfo(
        "kb_not_allowed", "Knowledge base not allowed", "The policy does not list this knowledge base.", "allowed_kbs", "policy",
    ),
    ReasonInfo(
        "tool_not_allowed", "Tool not allowed", "The policy does not list this tool.", "allowed_tools", "policy",
    ),
    ReasonInfo(
        "model_not_allowed", "Model not allowed", "The policy does not list this model.", "allowed_models", "policy",
    ),
    ReasonInfo(
        "token_limit", "Token limit exceeded", "The call would use more tokens than the policy allows for one request.",
        "max_tokens_per_request", "policy",
    ),
    ReasonInfo(
        "query_blocked", "Input blocked",
        "The input matched a guardrail: it was too long, held a blocked term, or looked like an injection or data theft attempt.",
        "blocked_terms", "guardrails",
    ),
    ReasonInfo(
        "rate_limit_exceeded", "Rate limit exceeded", "This identity sent too many requests in the current window.",
        None, "rate",
    ),
    ReasonInfo(
        "daily_token_budget_exceeded", "Daily token budget used up",
        "The tenant used its token budget for today. It resets at the next UTC midnight.", None, "budget",
    ),
    ReasonInfo(
        "cost_cap_exceeded", "Daily cost cap reached",
        "The tenant spent its daily cost cap. It resets at the next UTC midnight.", "daily_cost_cap_usd", "cost",
    ),
    ReasonInfo(
        "dependency_unavailable", "Service unavailable",
        "A service the check needs was down, so the call was stopped. Try again shortly.", None, "rate",
    ),
    ReasonInfo(
        "internal_error", "Internal error", "A check failed unexpectedly, so the call was stopped.", None, "enforce",
    ),
    ReasonInfo(
        "decision_unrecorded", "Decision not recorded",
        "The decision could not be written to the audit log, so the call was stopped.", None, "record",
    ),
)

REASONS: dict[str, ReasonInfo] = {r.code: r for r in _ENTRIES}


def all_reasons() -> list[ReasonInfo]:
    """The catalogue in a fixed order."""
    return list(_ENTRIES)
