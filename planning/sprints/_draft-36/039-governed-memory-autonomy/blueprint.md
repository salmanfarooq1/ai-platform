# Sprint 039: Blueprint

## Data (migration: next free number after Sprint 038's head)
- `agent_memory`: `id`, `tenant_id`, `agent_id`, `principal_id`, `content` (text), `content_sha256`, `source_kind` (user, tool, document, a2a, model), `source_ref`, `execution_id`, `decision_id`, `trust_tier` (high, medium, low), `status` (active, quarantined, deleted), `purpose`, `expires_at`, `created_at`. FORCE RLS. GRANT SELECT, INSERT, UPDATE (`status` only).
- `agent_autonomy`: `id`, `tenant_id`, `agent_id`, `tier` (0 to 3), `changed_at`, `changed_by` (principal or `system`), `trigger`, `decision_id`. Unique `(tenant_id, agent_id)` for the current row; history in `agent_autonomy_changes` (append only).
- `incidents`: `id`, `tenant_id`, `system`, `agent_id`, `severity` (incident, serious), `status` (open, assessed, reported, closed), `detected_at`, `aware_at`, `report_due_at`, `summary`, `decision_ids uuid[]`, `owner_principal_id`, `updated_at`. `incident_events` (append only) for each transition.
- `report_due_at` is `aware_at` plus `INCIDENT_REPORT_DAYS` for the incident class (a setting per class, validated in `core/settings.py`). The defaults are placeholders with a logged question, marked for the Sprint 043 check. No legal day count is hard-coded.
- Purge job: expired memory items move to `deleted` and lose `content`; the hash stays.

## Gateway
- New action kinds (introduced here): `memory.write`, `memory.read` (names from `planning/program/conventions.md`), `autonomy.change`, `incident.update`. All through `enforce()`.
- Trust tier from source: `user` with the run untainted is medium; `tool`, `document`, `a2a`, or any write in a tainted run is low. Policy may lower, never raise.
- `memory.write` runs the Sprint 038 guard stages on the content. A guard hit stores the item as `quarantined` and the decision is a deny `memory_quarantined`.
- `memory.read`: policy field `memory: {min_tier_by_purpose: {purpose: tier}}`. Recall returns only matching active items; the record v2 extension `memory` holds `{item_ids, min_tier}`.
- Autonomy tiers are policy data: each tier lists allowed tool classes and actions that need approval (Sprint 034). The tier is an input to the policy engine: `PolicyInput` (031) gains `autonomy: {tier}`. `tests/policy/decision_table.yaml` gets rows for both engines: each tier 0 to 3 with an allowed tool class, a blocked tool class, and an action that needs approval at that tier.
- Reason codes: `memory_quarantined`, `memory_tier_too_low`, `autonomy_tier_limit`.

## Autonomy job
- A worker job `autonomy_review` per agent per tenant reads: guardrail denies over a window, cost against the tenant's recent daily average, the last eval gate result.
- A breach lowers the tier by one. Thresholds are settings (`AUTONOMY_GUARD_HITS`, `AUTONOMY_COST_FACTOR`, `AUTONOMY_WINDOW_MINUTES`), validated. Their defaults are placeholders with a question in `planning/QUESTIONS.md`, not agreed rules.
- Each change writes an `autonomy.change` decision (so it is in the chain and has a signed receipt) and the event `platform.agents.autonomy.changed.v1`.
- `POST /v1/agent/{agent_id}/autonomy` (admin, with a reason) sets a tier. The job never raises a tier; only a human does. The change is an `autonomy.change` decision and an oversight event (Sprint 034).

## Contract
- `GET /v1/memory?agent_id&status&tier` (scope `agent` own items, `audit:read` all), `POST /v1/memory/{id}/release` (admin; moves quarantined to active at low tier), `DELETE /v1/memory/{id}` (admin; marks deleted).
- `GET /v1/agent/{agent_id}/autonomy`, `POST` as above.
- `GET /v1/incidents`, `POST /v1/incidents`, `PATCH /v1/incidents/{id}` (status transitions only, `audit:read` plus `admin`).
- OpenAPI snapshot refreshed.

## Events
`platform.memory.quarantined.v1`, `platform.agents.autonomy.changed.v1`, `platform.incident.changed.v1`. Ids and codes only.

## UI (follow `.claude/skills/governed-design/SKILL.md`)
- Governance > Agent memory: items with tier and status, quarantine queue, release and delete; per-agent tier with its history.
- Evidence > Incidents: list, detail with linked decisions, status transitions, the Art. 73 fields.

## Tests
- Integration: poisoned write quarantined; low-tier item excluded for a sensitive purpose; recall recorded; tier lowered on seeded guard hits and recorded; only a human raises a tier, and the agent's own run token cannot; incident transitions; RLS on all new tables; `test_decision_table_autonomy_tier_rows` (Python and OPA agree); `test_autonomy_route_singular` (`/v1/agent/{agent_id}/autonomy`); `test_autonomy_event_type` (`platform.agents.autonomy.changed.v1`).
- Playwright: quarantine queue and incident workflow.

## Docs
ADR-0028 (governed memory and autonomy tiers). `docs/operations.md` (incident runbook, autonomy settings). `planning/DOMAIN.md` terms: memory item, trust tier, autonomy tier, incident.
