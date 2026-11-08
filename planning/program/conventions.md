# Program 2 conventions

One list of names that every sprint pack uses. If a pack and this file disagree, this file wins. A Builder who must change a name records it here in the same pull request.

## Complete sprint delivery
Every sprint includes the applicable UI in the same sprint as its backend and contracts. The Architect identifies affected pages, navigation, forms, decisions, receipts and operator journeys before assigning the Builder. Ship their real API integration, permissions, loading/empty/error states, keyboard/reduced-motion behavior and an end-to-end journey within that sprint. Do not defer applicable UI to a later polish sprint. Infrastructure-only work may need no new page; record that assessment and verify any existing UI journey it changes or restores. Acceptance requires both backend and applicable UI evidence.

## Scripts and checks
| What | Name | Created in |
|---|---|---|
| Licence gate | `scripts/supply_chain/licence_gate.sh` | 011 |
| SBOM | `scripts/supply_chain/sbom.sh` (CycloneDX for Python and npm) | 011 |
| Skip guard | `poetry run python scripts/check_skips.py <junit.xml>` reading `tests/skip_allowlist.json` (the expected count comes from the allowlist) | 011 |
| Secret scan | gitleaks CLI in CI | 011 |
| Pre-flight | `scripts/preflight.sh` (engine, memory, clock, ports) | 011, extended in 017 |
| Import boundaries | `poetry run lint-imports` (import-linter contracts in `pyproject.toml`) | 012 |
| Edition smoke | `scripts/ci/edition_smoke.sh` runs `ENABLED_MODULES=<edition> poetry run pytest -m edition_smoke` for each edition; CI workflow `.github/workflows/editions.yml` calls it | 012 |
| Model lock check | `scripts/models/check_lock.sh` against `models.lock` | 013 |
| Live verify scripts | `scripts/verify/<component>.sh` | per sprint |
| Showcase journeys | `scripts/showcase/<milestone>.sh` and `ui/e2e/showcase-<milestone>.spec.ts` | 014 onward |

## Modules and editions
- `ENABLED_MODULES` values: `gateway`, `evidence`, `agents`, `data`, `lineage`, `insights`, or `all`. `insights` needs `data`; startup refuses it alone. The `insights` value and the Data edition's `insights` part start in 029. Before then Data is `gateway,data,lineage`. `gateway` is always on.
- Editions: Gateway (`gateway`), Assurance (`gateway,evidence`), Agents (`gateway,agents`), Data (`gateway,data,lineage,insights`), Full (`all`).
- Packages: `evidence/` (012), `dataplane/` (021), `lineage/` (025), `insights/` (029). Other modules may import the `gateway` package API (`gateway/__init__.py`) but not its internals.

## Scopes (credentials)
Existing: `kb:read`, `kb:write`, `query`, `agent`, `audit:read`, `admin`.

New in program 2:
| Scope | Grants | Added in |
|---|---|---|
| `data:read` | Query and preview data the caller has a grant or ownership for | 021 |
| `data:write` | Uploads, pipeline definitions and runs, dbt runs | 022 |
| `data:steward` | Contracts, certification, access approvals, quality rule approval | 023 |
| `insights:write` | Create, edit and publish dashboards; subscribe other principals to reports | 029 |
| `approvals:decide` | Decide runtime action approvals | 019 |
| `policy:write` | Publish and test policies (today `admin`) | 018 |

`GET /v1/system/modules` uses metadata-only `system.read` (012), granted by each recognized existing scope and enforced after scope-union authentication. It grants no KB/model/audit operation; empty/unknown scopes remain denied.

## Action kinds (gateway)
Existing: `kb.read`, `kb.write`, `model.invoke`, `tool.call`, `agent.run`, `feedback.write`, `analytics.read`, `audit.read`.

New: `system.read` (012, platform metadata only), `data.read` (021), `data.write` (022), `data.extract` (024), `product.certify` (023, used by 023 for certification and by 029 for metrics), `access.request`, `access.approve`, `access.revoke` (024), `lineage.read` (025), `dashboard.write` (029), `report.write`, `report.deliver` (029), `approval.decide` (019), `agent.stop`, `agent.override` (019), `memory.write`, `memory.read` (028), `evidence.export` (030).

Also added by their sprints: `document.review` (026), `session.create` (020), `delegation.exchange` (020), `a2a.call` (028), `output.check` (019), `autonomy.change`, `incident.update` (028), `evidence.pack`, `evidence.system.update` (030), `evidence.assessment.upload` (030), `observability.read` (030).

Stage pipeline order (first deny wins). Sprint 013 order is `principal` → `module` → `boundary` → `model` → `policy` → `guardrails` → `rate` → `budget` → `cost`. The `model` stage follows `boundary` so a caller without scope is denied first. Later sprint stages slot into this order: `peer` (028) after `boundary`; `purpose` (018), `query` (024), `duties` (023, extended in 024; also reports `certification_blocked`), `grant` (024), `taint` (027), and `pii` and `guard` (019) before `rate`. `approval` (019) is called from `policy` for actions whose verdict is `approval_required` and checks a bound approval at execution. For `surface` `dashboard`, `report` or `alert`, `approval_required` becomes a withheld tile and no approval row. `duties` is extended in 019 to `approval.decide` (self-approval is `separation_of_duties`).

Principal precedes module so missing credentials/scopes keep their existing 401/403 behavior before an authenticated disabled-module denial.

The one accepted exception to "every call recorded" (015): during maintenance capture, non-health requests receive 503 `maintenance` before `enforce()` and write no decision row, because the database is being captured. Turning maintenance on and off is itself a recorded decision.

The ask-your-data answer has no action kind of its own. Its receipt fields ride on the answer step's `model.invoke` decision (request path step 9).

### Action-to-module map
The `module` stage (012) needs each action kind's module. Each sprint registers its own kinds: `data.*`, `access.*`, `product.certify` → `data`; `lineage.read` → `lineage`; `dashboard.write`, `report.*` → `insights`; `agent.*`, `tool.call`, `memory.*`, `document.review` → `agents`; `evidence.*` → `evidence`. Everything else → `gateway`.

### Decision record v2 extensions
| Extension | Fields | Added in |
|---|---|---|
| `model` | name, provider, source, digest or provider model id, processing scope, route fingerprint, phase | 013 |
| `stages` | ordered stage, status, reason and duration entries for every decision | 013 |
| `data` | `snapshot_id` | 021 |
| `data` (more) | `quality_evaluation_id` | 023 |
| `access` | request id, grant id | 024 |
| `query` | `sql_sha256`, grant ids and version, withheld columns, row filter ids | 024 |
| `query` (more) | `metric_ids`, `estimate_rows` | 025 |
| `insight` | `dashboard_id`, `dashboard_version`, `tile_id`, `view_id` | 029 |
| `on_behalf` | `initiator`, `subscription_id`, `job_id` | 029 |
For `model`, the closed schema fields are `name`, `provider`, `source`, exactly one of `digest` or `provider_model_id`, `processing_scope`, `route` and `phase` (`admission` or `attempt`). For `stages`, each entry is `{stage, status, reason, duration_us}`. Status is `passed`, `denied`, `skipped` or `not_reached`. Later sprints add their own extension and list it here.

Sprint 013 reason codes: `model_breaker_open` (model), `model_concurrency_limit` (rate), `data_use_not_allowed` (policy), and `verifier_must_be_local` (policy).

### Ports
`DataAccess` grows by sprint: `read` (012 skeleton, 021 adapter), `current_snapshot` (021, one tenant catalog snapshot id), `extract` (024), `list_metrics`, `describe_metric`, `query_metric(..., snapshot_id, purpose, surface)` (025), `metric_catalog` (029), `submit_write` (026). `LineageLookup` (`upstream`, `downstream`) comes in 025. Each change extends the port's contract suite on both adapters. `DecisionSink` and `EvidenceLookup` are always real in production, including with M2 off. The 012 no-op `LineageEmitter` drops/counts only; 022 introduces a durable tenant-scoped spool before production emitters ship, and 025 consumes it.

## Events and jobs
- CloudEvent types: `platform.<area>.<thing>.<past-verb>.v1`, for example `platform.data.snapshot.committed.v1` (022), `platform.insights.report.delivered.v1` (029). Kafka topic names drop the `.v1`.
- Job kinds: `<module>.<thing>.<verb>`, for example `insights.report.run`, `insights.alert.check`.

## Settings
- Module prefix first, unit spelled out: `INSIGHTS_REPORT_RETENTION_DAYS`, `INSIGHTS_VIEW_TIMEOUT_SECONDS`. Existing names stay as they are.

## ADR numbers
ADR numbers are reserved by the plan in `vision-and-architecture.md`. A sprint may write a higher number before a lower one exists (ADR-0031 in 029).

## Routes
- Product routes stay under `/v1`.
- The only exception is rule 9 in `vision-and-architecture.md`: public discovery documents under `/.well-known/` (RFC 9728 metadata in 016, AuthZEN discovery in 018, A2A Agent Card in 028).
- Data plane routes: `/v1/data/...` (datasets, pipelines, products, quality), `/v1/semantic/...`, `/v1/lineage/...`.
- Insights routes: `/v1/insights/...` (metrics catalog, dashboards, subscriptions, alerts, runs). The inbox is a kernel feature: `core/inbox.py`, `/v1/inbox`, built in 019 for approvals. Reports (029) also post to it. The 019 list of pending approvals is the "approval queue".
- Access requests, listings and grants: `/v1/access/...` (024).
- Receipts: `/v1/receipts/{decision_id}`. Agent routes stay singular: `/v1/agent/...`.
- Approvals: `/v1/approvals` (runtime approvals from 019 and access requests from 024 share the model, defined in 019, and the route, with a `kind` field: `access_request`, `runtime_action`).
- Operator-only routes (AuthZEN evaluation, MCP and A2A registry admin, memory and autonomy admin) use `admin`. A narrower scope is a later decision.

## Placeholders
Numbers that are business decisions (retention days, thresholds, k values, quality weights, guard precision and recall, autonomy triggers) are placeholders in the packs. Each Builder writes them as settings with a default, logs a question in `planning/QUESTIONS.md`, and never presents them as agreed rules.
