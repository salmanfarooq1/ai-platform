# Sprint 034: Blueprint

## Contract
- New scope `approvals:decide` (introduced here; the name is in `planning/program/conventions.md`). Add it to `Scope` in `core/identity/models.py`. `admin` still satisfies it.
- `GET /v1/approvals?kind=runtime_action&status=pending` (`approvals:decide`): the approval queue. It is the shared `/v1/approvals` route and model from Sprint 023, with the `kind` field: 023 uses `access_request`, this sprint adds `runtime_action`. Items have the 023 shape `{kind, subject_id, step, subject_hash, ...}`. For `runtime_action`, `subject_id` is the approval id (`action_approvals.id`, the value of `Approval-Id`) and `subject_hash` is its `action_hash`. A caller sees only the kinds its scopes can decide (`data:steward` from Sprint 021 for `access_request`, `approvals:decide` for `runtime_action`).
- `GET /v1/approvals/{subject_id}?kind=runtime_action` (`approvals:decide`): the approver view. Fields: `action_hash`, `action_kind`, `resource`, `evidence` (normalised SQL or tool arguments, datasets and columns touched, withheld columns, estimated rows and cost, policy reason code and sentence), `requester`, `purpose`, `expires_at`, `status`. No field holds agent-written text.
- Decide: the Sprint 023 route and body, `POST /v1/approvals/{subject_id}` with `{kind: runtime_action, decision, subject_hash, note}`. `subject_hash` is the `action_hash`. The caller needs `approvals:decide` (CSRF for cookies). 403 `separation_of_duties` when the caller is the requester (the 023 code). 409 `step_already_decided` when not pending (the 023 code). 409 `request_changed` on a hash mismatch, as in 023.
- Re-submit: the caller sends the same request with header `Approval-Id: <uuid>`. The agent tool layer and MCP pass it the same way.
- A gated call answers 202 `ApprovalPending {approval_id, action_hash, expires_at}`. A route that cannot answer 202 answers 403 with code `approval_required`, and the approval id is in the `Approval-Id` response header.
- `POST /v1/agent/runs/{execution_id}/stop` and `/override` (body `{reason}`, 500 chars max). Scope `agent` for the run's own principal, or `admin`. 404 `run_not_found` for a foreign run (same body as missing). 409 `run_finished` for stop on a finished run.
- AuthZEN (032): an approval-required evaluation returns `decision: false` with `context.approval {id, status, expires_at}`. Docs and OpenAPI label it "draft-compatible".
- OpenAPI snapshot refreshed.

## Data (migration: next free number after Sprint 033's head)
- `action_approvals`: `id` (the approval id; it is the `subject_id` of its rows in the Sprint 023 `approvals` table), `tenant_id`, `action_hash` (hex SHA-256), `action_kind`, `resource`, `evidence jsonb`, `requester_principal_id`, `execution_id`, `request_decision_id`, `expires_at`, `used_at`, `used_by_decision_id`. FORCE RLS. GRANT SELECT, INSERT, UPDATE (`used_at`, `used_by_decision_id` only) to `gap_app`.
- `oversight_events`: `id`, `tenant_id`, `kind` (approve, reject, stop, override, expire), `actor_principal_id`, `execution_id`, `approval_id`, `decision_id`, `reason`, `at`. Append only: GRANT SELECT, INSERT.
- Widen the `approvals.kind` CHECK from Sprint 023 to `('access_request', 'runtime_action')`. A decision on a runtime action is an `approvals` row with `kind = 'runtime_action'`, `subject_id = action_approvals.id` and `subject_hash = action_hash`.
- `jobs.output_withheld boolean` for override.

## Gateway
- `gateway/approvals.py`: `canonical_action(...)` builds the hashed object; `action_hash()` is SHA-256 of `canonical_json` (the evidence core's canonical form). SQL is normalised with sqlglot (duckdb dialect) before hashing.
- Code fact from Sprint 031: the policy stage turns an `approval_required` verdict into a deny with that reason, and the reason code already exists. Change that branch: the policy stage hands the verdict to `gateway/approvals.check()`, recorded with stage `approval`. With no `Approval-Id`: create the request, deny `approval_required`. With one: consume it in one statement (`UPDATE ... SET used_at = now() WHERE id = $1 AND action_hash = $2 AND used_at IS NULL AND expires_at > now() RETURNING id`, joined to an approving `approvals` row with `kind = 'runtime_action'` for that `subject_id`). No row: deny `approval_not_valid` (one code for unknown, used, expired, rejected and changed; the log line says which). With a valid approval the policy stage returns no decision, so the later stages (guardrails, rate, budget, cost) run as usual.
- A spent approval stays spent if the decision write fails (fail closed: ask again).
- Expiry `APPROVAL_TTL_SECONDS` (default 900, max 3600) and `APPROVAL_MAX_PENDING` per principal (default 20), validated in `core/settings.py`. Both defaults are placeholders with a question in `planning/QUESTIONS.md`. Over the cap: deny `approval_required` with no new row.
- Reason codes in `gateway/reasons.py` (`approval_required` exists): add `approval_not_valid`, `run_stopped`, `run_overridden`. Self-approval reuses `separation_of_duties` and a closed step reuses `step_already_decided` from Sprint 023. New action kinds (introduced here; names from `planning/program/conventions.md`): `approval.decide` (a runtime approval decided), `agent.stop`, `agent.override`, each through `enforce()`. Access requests keep `access.approve` from Sprint 023. The 023 `duties` stage extends to `approval.decide`.
- Record v2 extension `approval`: `{approval_id, action_hash}` on the consuming decision.
- Sprint 026 guard: over the row or cost limit returns approval required, not deny.
- Surfaces: when the context `surface` is `dashboard`, `report` or `alert`, the approval check creates no `action_approvals` row and no `approvals` row. The decision is a deny `approval_required` and the tile renders `withheld`.
- Inbox: a new runtime approval posts an `approval_pending` item to the kernel inbox (`core/inbox.py`, `/v1/inbox`, Sprint 029) for each principal that can decide it. The item holds ids only. No new inbox table or route.

## Events
`platform.approvals.requested.v1`, `platform.approvals.decided.v1`, `platform.agent.run.stopped.v1`, `platform.agent.run.overridden.v1`. Ids and codes only, no evidence text.

## MCP
A tool call that needs approval sends an elicitation. Classified data or any SQL: URL mode, pointing at the console approval page. Otherwise form mode, which only shows the approval id and status. The approval itself is always given by an approver in the console.

## UI (follow `.claude/skills/governed-design/SKILL.md`)
- Governance > Approvals: "Runtime actions" tab (approval queue, approver view with an evidence panel, approve and reject with a reason), "Oversight log" tab.
- Governance > Agent runs: Stop and Override buttons with a confirm dialog; an overridden run shows "Output withheld".

## Tests
- Unit: hash stability and sensitivity per field; stage order; reason codes in the catalogue.
- Integration: `approvals:decide` needed to decide a runtime action, and `data:steward` alone cannot; reuse refused; changed SQL refused; expired refused; self-approval 403 `separation_of_duties`; decided step 409 `step_already_decided`; `test_no_approval_rows_from_dashboards` (`approval_required` on a dashboard, report or alert surface gives `withheld` and no approval rows); `test_approval_pending_posts_inbox_item`; a policy deny after approval still denies; concurrent consume (two tasks, one wins); RLS on both tables as `gap_app`.
- MCP elicitation through the 2026-07-28 transport with an in-process client.
- e2e: the salary journey (analyst persona asks, steward approves, re-run answers). The steward persona's key in the Sprint 015 fixtures gains `approvals:decide`. Playwright: approval queue, approver view, stop.
- Named tests per acceptance item in `acceptance.md`.

## Docs
ADR-0024 (human approvals bound to the action hash). `docs/api/` approvals page. `docs/operations.md` (stop and override). `planning/QUESTIONS.md` Q22 closed.
