# Sprint 031: Builder brief
You are the Builder for Sprint 031 in `/home/ubuntu/ai-platform`, on branch `sprint/031-policy-engine-opa`. This is a vertical slice: the seam and contract, the OPA adapter and bundle, evidence, UI and an e2e test. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, and this folder (all five files).
- `gateway/policy.py`, `gateway/stages.py` (`ENGINE` is set at module level) and `gateway/enforce.py` (`STAGES`).
- ADR-0006 and ADR-0012, the record v2 rules in ADR-0013, and the 024 purpose stage.
- `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
Everything in the blueprint, in this order: the seam move to `ports/policy.py`, the `PolicyInput` builder, the Rego bundle and decision table, the OPA adapter and registry selection, the migration and evidence extension, routes, the replay script, the compose profile, UI.

## Tests
- **Baseline:** the numbers in Sprint 030's report. State the delta.
- Write one test per acceptance item and per threat-model row, using the names given there.
- The OPA HTTP path runs against a fake OPA server in pytest. The Rego runs through the pinned static `opa` binary (`opa eval`, `opa test`), which needs no server.
- Install the binary by checksum in the composite CI setup action and locally. Do not skip when it is missing.
- The live sidecar run is `scripts/verify/opa.sh`. Add no new skips.

## Notes from the Architect
- **Pins:**
  - Image `openpolicyagent/opa:1.20.2-static`, pinned by digest.
  - The same version for the CLI binary, with its SHA-256.
  - Record both in `evidence/pins.txt`.
- **Code facts:**
  - `PolicyEngine.evaluate(boundary, action)` has no purpose or principal today. Widen it with `PolicyInput`.
  - Keep a thin wrapper so `PythonPolicyEngine` behaviour is the same on every existing test.
- **Tool arguments:** never send raw arguments to OPA or store them. The gateway checks the JSON Schema as today and passes only the result and the hash.
- **No behaviour change:** the full existing suite must pass unchanged with `POLICY_ENGINE=python`. Run it once more with `POLICY_ENGINE=opa` against the fake OPA that evaluates the real bundle through `opa eval`, and record the result.
- **Signing key:**
  - The bundle signing key comes from a file path in `POLICY_BUNDLE_SIGNING_KEY_FILE`, never from the repo.
  - Local mode generates a throwaway key pair at build time and logs only its key id.
- **Q15:** write the proposed display rule into QUESTIONS for the owner to confirm. Build it as written.
- **Migration:** use the next free number after Sprint 030's head.
- **Docs:** ADR-0022, `docs/runbooks/opa.md`, `docs/configuration.md`, `docs/operations.md`, OpenAPI snapshot, `.env.example`, CHANGELOG (with the test delta), STATE, QUESTIONS (Q8, Q15).

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run pytest -q -rs --junitxml=planning/sprints/031-policy-engine-opa/evidence/pytest.xml
POLICY_ENGINE=opa poetry run pytest -q -rs tests/policy tests/integration
poetry run python scripts/check_skips.py planning/sprints/031-policy-engine-opa/evidence/pytest.xml
docker compose --profile policy config -q && scripts/verify/opa.sh
poetry run python scripts/update_openapi.py
scripts/supply_chain/licence_gate.sh
scripts/ci/edition_smoke.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`.

Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names, no model or tool attribution. Use simple sentences in docs.

## Finish
Write `report.md` with:
- the acceptance table with evidence links
- the test numbers and the delta against Sprint 030
- the migration number
- the OPA memory
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(policy): move the policy seam to a port with three outcomes`
- `feat(db): store policy inputs and bundles for replay`
- `feat(policy): add opa adapter, signed bundle and decision table`
- `test(policy): run one decision table on both engines`
- `feat(ui): show policy engine and persona policies`
- `chore(ops): add opa policy profile and verify script`
- `docs(adr): record opa behind the policy seam`
- `docs(planning): update state, questions and changelog for the policy engine`

The Builder does not commit. A human runs the commands.
