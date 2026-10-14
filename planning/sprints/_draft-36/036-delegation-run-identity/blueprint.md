# Sprint 036: Blueprint

## Spike (branch `spike/036-token-exchange`, never merged)
Run Keycloak from the Sprint 035 profile in a throwaway compose profile `identity-spike`. Start it with the preview feature `--features=token-exchange-delegation`, which RFC 8693 delegation (`actor_token`, nested `act`) needs. Never set it in the `identity` profile. Enable standard token exchange v2 on a test client. Call the token endpoint with `subject_token`, `actor_token` and `audience`. Record: accepted or refused, the claims of the result, whether `act` is present and nested. Save the commands and raw output (tokens redacted) in `evidence/spike-token-exchange.md`. Decided 2026-10-11: the platform-minted adapter is the default. Keycloak becomes the default only if the spike passes and nested delegation is no longer a preview feature at sprint start.

## Ports and adapters
- `ports/delegation.py`: `DelegationIssuer` with `exchange(subject, actor, audience, scopes, not_after) -> DelegationToken` and `verify(token, audience) -> DelegationChain`. Frozen dataclasses, no SDK.
- `adapters/platform_delegation.py`: mints EdDSA JWTs with `DELEGATION_SIGNING_KEY_FILE`. The default (decided 2026-10-11).
- `adapters/keycloak_delegation.py`: RFC 8693 exchange at the provider. Built only if the spike passed and the feature is no longer preview; otherwise not written, and the ADR says why.
- Registry picks by `DELEGATION_ISSUER` (`platform` or `keycloak`). Contract suite in `tests/contracts/test_delegation_contract.py`.

## Token shape
`iss` (platform or provider), `sub` (the user principal), `aud` (exactly one downstream: `gateway`, `mcp:<server id>`), `scope` (space separated), `exp`, `iat`, `jti`, `tenant_id`, `act: {sub: <spiffe run id>, act: {...earlier actor}}`. `may_act` on the subject side names who may act for it.

## Rules (in `core/identity/delegation.py`)
- `may_act`: the subject's `may_act` (from the provider claim, or from the tenant policy field `may_act`, a list of agent ids) must name the actor. Else deny `delegation_not_permitted`.
- Audience: one value, from an allow-list of downstreams. Else deny `delegation_audience`.
- Lifetime: `exp` is the earlier of the run's end (run token expiry) and `DELEGATION_MAX_TTL_SECONDS` (default 900). A token past its run is refused with `delegation_expired`.
- Narrowing: requested scopes must be a subset of the caller's. Else deny `delegation_widening`. Nesting depth at most `DELEGATION_MAX_DEPTH` (default 3).
- Settings validated in `core/settings.py`: the key file, `SPIFFE_TRUST_DOMAIN` (a DNS-style name, default `platform.local`), the two limits.

## Report runs (029)
- A report or alert run takes a delegation token with `sub` = the recipient, `act: {sub: job:insights.report.run}` and `aud` = `gateway`.
- The recipient's `may_act` names `insights.report` (a platform default for subscribers). Without it the run is denied `delegation_not_permitted`.
- The 029 `on_behalf` extension stays. The `delegation` extension carries the same chain.

## Contract
- `POST /v1/sandbox/runs/{execution_id}/delegate` (run token): body `{audience, scopes}`; returns `{token, expires_at}`. The token is shown once and never stored; only its `jti` hash is kept.
- `GET /v1/agent/runs/{execution_id}` gains `run_id` (SPIFFE form) and `delegation_chain` per decision.
- OpenAPI snapshot refreshed.

## Data (migration: next free number after Sprint 035's head)
- `delegation_tokens`: `id`, `tenant_id`, `execution_id`, `jti_sha256`, `subject_principal_id`, `actor_run_id`, `audience`, `scopes`, `expires_at`, `revoked_at`. FORCE RLS. GRANT SELECT, INSERT, UPDATE (`revoked_at`). Run stop (Sprint 034) also revokes these.

## Gateway
- New action kind `delegation.exchange` (introduced here) through `enforce()`. Reason codes: `delegation_not_permitted`, `delegation_audience`, `delegation_expired`, `delegation_widening`.
- Record v2 extension `delegation`: `{run_id, chain: [{sub, aud, scopes, jti_sha256}]}` on every decision with an `execution_id`.
- `PolicyInput` (031) gains `delegation: {depth, chain: [{sub, aud, scopes}]}`. No token text. `tests/policy/decision_table.yaml` gets rows for both engines: no chain, depth at the limit, an actor not in `may_act`, and a report run (`act=job:insights.report.run`).

## UI (follow `.claude/skills/governed-design/SKILL.md`)
Run view: the chain as a short list (user, then run, then downstream), each hop with scopes and expiry. Decision rows show the hop that made them.

## Tests
- Contract suite on the platform adapter (and Keycloak if built).
- Unit: SPIFFE id format and parsing; nested `act` build and read; narrowing table.
- Integration: `test_report_run_delegation_chain` (a report run carries `sub=recipient`, `act=job:insights.report.run`); `test_decision_table_delegation_rows` (Python and OPA agree); `test_identity_profile_has_no_preview_features`; widening refused and recorded; `may_act` missing refused; wrong audience refused; token after run end refused; chain on every run decision; RLS on `delegation_tokens`.
- Playwright: run view shows the chain.

## Docs
ADR-0025 (external identity provider and delegation; covers the Sprint 035 provider choice, this sprint's spike result, and the 2026-10-11 decision: platform-minted by default, no preview features in the default stack). `docs/architecture.md` identity section. `docs/operations.md`: SPIRE as an optional step.
