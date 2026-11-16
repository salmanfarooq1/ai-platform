Implemented public policy CAS and concurrency-safe version allocation, injected Ollama routing, thin restore, and drift guards.
Red evidence: `evidence/demo-drift-red.txt`.
Checks: 64 requested unit tests and 37 isolated refco integration tests passed, including restore, concurrent CAS and zero inference.
Full backend Ruff, mypy on five changed product modules, and all 7 import contracts passed; green output is in `evidence/demo-drift-*.txt`.
Updated product docs, generated settings reference, MAP and CHANGELOG; deleted the stray root report.
No commits; rag_platform data untouched; integration used tests/harness throwaway databases.
Proposed human commands (review existing worktree changes before staging):
`git add -p gateway/admin.py core/settings.py adapters/litellm_llm.py adapters/registry.py pyproject.toml tests/unit/test_llm.py tests/integration/refco/test_m0.py docs planning/MAP.md CHANGELOG.md`
`git add tests/unit/test_gateway_admin.py tests/unit/refco/test_public_seams.py tests/integration/refco/test_policy_cas.py`
`git commit -m "fix(gateway): keep showcase policy and model routing on public product seams"`

## Final independent-review fixes
All four findings are addressed; existing history, isolation and zero-inference assertions remain.
Showcase code contains no product-table SQL, including persona setup; the AST guard fails on the former queries.
The auditor finds both denials through `/v1/console/decisions?request_id=...`, using its own credential.
Product change: this path aliases the existing handler, preserving audit scope, enforcement and tenant isolation.
A standalone Gateway audit client needs the same read capability; the integration test proves scope and foreign-tenant rejection.
Product change: public identity admin functions inspect active credentials, tenant inventory and principal key metadata, and lock operator workflows.
Deployment preflight and credential recovery clients need these general reads without SQL or stored-hash exposure; fixture rules stay in the showcase.
Free-text redaction is deleted. Failure output uses fixed reasons and exception class names, capped at 300 characters.
Complete server stderr stays in exclusively created, git-ignored `.showcase/m0-server.log`, mode 0600; archive it privately before a rerun.
Tests cover DSN passwords containing @, alphabetic tokens, JSON passwords, Bearer values and journey exception messages.
Baseline publication expects the observed head (or 0); deny publication expects the new baseline. PolicyConflict stops without overwriting.
Writer A holds its publication uncommitted while B must remain unfinished; CAS and unconditional writes cover absent and existing heads.
Red evidence: `evidence/review-final-red.txt`: 79 failed/25 passed, then 2 failed/3 passed, 5 operator failures, and 2 integration failures/41 passed.
The initial default-port operator attempt skipped; rerunning on the actual stack captured all five failures before implementation.
Green: 211 unit tests and 43 refco integration tests passed; integration ran alone against throwaway `gap_test_*` databases. MAP checks: 2 passed.
Full backend/showcase Ruff, mypy (172 sources), lint-imports (7 contracts), generated UI typecheck and diff checks passed; outputs are `evidence/review-final-*.txt`.
Updated API docs, OpenAPI, generated TypeScript types, operations, showcase instructions, sprint scope/blueprint, MAP and CHANGELOG.
No commits or pushes; `rag_platform` data and `ai-platform_pgdata` were untouched.
Proposed human staging, after reviewing the existing worktree: `git add -p api/routers/console.py core/identity/admin.py docs ui/src/api/schema.d.ts planning/MAP.md CHANGELOG.md scripts/showcase/README.md`
Then: `git add scripts/showcase/m0.py scripts/showcase/personas.py tests/unit/refco tests/integration/refco/test_m0.py tests/integration/refco/test_m0_restore.py tests/integration/refco/test_operator_reads.py tests/integration/refco/test_policy_cas.py planning/sprints/014-reference-company`
Proposed human commit: `git commit -m "fix(gateway): close showcase public seams and diagnostics findings"`

## Product overreach correction (supersedes the alias and inventory additions above)

Lines before → after: personas 471 → 251; identity admin 243 → 214; M0 362 → 363; console 509 → 508; persona integration tests 519 → 377.
Removed `/v1/console/decisions`; auditor clients use `/v1/decisions?request_id=...`. Regenerated OpenAPI/TypeScript and removed alias documentation.
Removed product functions `identity_admin_lock`, `tenant_inventory` and `principal_keys`; no global writer lock or replacement product lock remains.
Added `list_principals`: a second provisioning/reconciliation client needs the general read counterpart to `create_principal`, including disabled state and tenant isolation.
Added `list_kbs`: a second owner-role inventory client needs the counterpart to `create_kb` without a running API; `/v1/config` only exposes runtime-policy-visible KBs.
Kept narrow `inspect_credential`: an operator credential checker needs tenant ID/slug, principal ID/kind, prefix and scopes; never database, KBs, secret or hash.
Extended existing `list_keys` with optional principal filtering: any rotation client needs tenant-bound key metadata; no duplicate recovery function is needed.
Setup finds principals by name, reuses verified keys or rotates and revokes owned prefixes, and atomically writes private keys plus tenant-bound prefix/scope-hash metadata. Claim, journal and freshness checks are gone.
Kept only the showcase-local file lock: concurrent setup processes must not overwrite each other's private key files.
M0 drops the database-name check: a verified credential must match the manifest tenant UUID and slug; a database name adds no identity guarantee and changes across restores. KBs use the separate public read.
Removed `test_refuses_non_fixture_tenant` (8 cases): these specified the deleted claim marker/freshness protocol; credential/manifest tenant isolation remains tested.
Removed `test_interrupted_run_is_recoverable` (4 cases): these specified the deleted durable intent protocol; failed issuance now rolls back its operator transaction.
Removed `test_process_death_between_renames_is_recoverable` (2 cases): these specified journal-based crash recovery; reruns validate saved keys and rotate invalid ones.
Retained security/path/secret tests and principal-identity assertions through credential inspection; added foreign-key non-revocation and manifest tenant tests. Zero-inference, policy-history and receipt assertions remain intact.
Red: `evidence/overreach-red.txt` captures 8 unit and 10 identity/persona failures, then the full-tier docs failure and the isolated child-cache startup failure.
Green: full `pytest -m unit` passed 1183 tests; `pytest tests/integration/refco` ALONE passed all 34, including the 7 touched identity operator tests, with no skips.
Ruff, full mypy (172 sources), lint-imports (7 kept), generated UI typecheck and generated-doc checks passed; evidence is `evidence/overreach-*.txt`. The seventh contract has a seeded product-imports-scripts failure case.
Fixed the prior OLLAMA_BASE_URL documentation grouping without weakening its assertion; the M0 test child now inherits tests/harness.REDIS_URL explicitly, with no product workaround.
No commits/pushes. Only tests/harness throwaway databases were used; rag_platform and ai-platform_pgdata were untouched.
Proposed human staging after reviewing the existing worktree: `git add -p core/identity/admin.py tests/unit/test_import_contracts.py scripts/docs/generate.py docs ui/src/api/schema.d.ts planning/MAP.md CHANGELOG.md`; `git add scripts/showcase tests/unit/refco tests/integration/refco planning/sprints/014-reference-company`.
Proposed human commit: `git commit -m "refactor(identity): remove showcase-only product helpers and simplify persona setup"`.

## Six-finding review (five fixed; finding 2 awaits migration scope)
1. HIGH key rotation: revoke only the manifest's issued prefix; preserve other active keys and WARN with counts/prefixes.
   Test: test_identity_key_listing.py::test_persona_rotation_preserves_foreign_key (saved state, lost state, lost manifest: all pass).
2. MEDIUM list_keys: resolve tenant and establish _as_tenant before reading; None is documented operator-wide listing.
   Test: test_list_keys_sets_tenant_on_fresh_app_connection (both cases fail: tenants RLS hides the slug before UUID resolution).
   Blocker: a general SECURITY DEFINER tenant-ID lookup needs a migration, excluded by sprint requirements; scope decision requested in planning/QUESTIONS.md. No test/RLS weakening.
3. MEDIUM seams: recursive AST guard bans database methods/imports and generic SQL literals; private-import guard retained.
   Tests: test_sql_guard_recognizes_any_table, test_sql_guard_rejects_calls_without_literal_sql, test_sql_guard_rejects_database_imports, test_private_import_guard_rejects_seeded_sources.
4. LOW policy overlap: observe B's backend in pg_stat_activity waiting on Lock before releasing A; timeout fails.
   Tests: test_two_concurrent_policy_writers (all four pass), test_wait_for_lock_observes_backend_before_returning, test_wait_for_lock_timeout_fails.
5. LOW catalog helper: construction moved into recorder test; removed create_catalog from m0_server.py.
   Test: test_server_entrypoint_has_no_adapter_construction; M0 recorder integration deferred as requested.
6. LOW shell runner: Poetry on PATH by default; SHOWCASE_PYTHON retained; missing runner explains both options.
   Test: test_m0_shell_resolves_runner (PATH, override and missing); README updated.
Red evidence captured before fixes; corrected a mock and filename collision without weakening assertions. SQL seed now also tests multiline DDL without tripping the repo scanner.
Ordered checks: pytest -m unit -q: 1214 passed. Selected policy CAS + new identity file: 8 passed, 2 failed (finding 2 blocker).
ruff check .: 468 existing errors in 44 tracked files unchanged from HEAD; touched-file Ruff passes. mypy: 172 sources pass. lint-imports: 7 kept, 0 broken. git diff --check passes.
Evidence: evidence/review-six-*.txt. No full refco tier, Playwright, Valkey cleanup, commit or push.
Proposed human staging after resolving finding 2: git add -p core/identity/admin.py scripts/showcase docs/operations.md CHANGELOG.md planning/MAP.md planning/QUESTIONS.md; git add tests/unit/refco/test_public_seams.py tests/unit/refco/test_review_regressions.py tests/integration/refco/test_identity_key_listing.py tests/integration/refco/test_policy_cas.py tests/integration/refco/test_m0.py planning/sprints/014-reference-company
Proposed human commit after resolution: git commit -m "fix(identity): preserve foreign keys and harden reference-company public seams"

## Close (Architect, 2026-11-16)
- Finding 2 resolved without a migration: `admin.*` is an owner-role module by contract. The test now checks that `list_keys` sets the tenant context on a fresh owner connection (both tenants pass).
- `accept.sh` 8/8 PASS: ruff, mypy (172), contracts (7 kept), unit 1214, refco 39, UI types, Playwright showcase-m0, live M0 on real Ollama. Evidence: `evidence/checks.txt`, `evidence/accept-*.log`.
- No weakened tests vs 013 (only change: contracts "6 kept" → "7 kept").
- Second-client check on product diff: identity inventory reads, `inspect_credential`, policy compare-and-swap, `ollama_base_url` setting. All general operator functions.
- Removed `evidence/review-six-ruff.txt` (whole-tree noise). CI ruff paths now include `scripts/showcase`.
- Carry to 015: make the legacy `generate_with_citations` caller required (fail closed); restore drill.
