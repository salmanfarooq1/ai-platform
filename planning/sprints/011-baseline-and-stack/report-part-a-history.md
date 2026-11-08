# Sprint 011 report

**Status: Sprint 011 remains blocked; corrective implementation and verification are ready for Architect re-review.** Branch: `sprint/011-baseline-and-stack`, created locally from `planning/sprint-plans`. No commit, push, merge, pull or main-branch switch ran. Unrelated root files and the Architect's review/probes are preserved.

## Part a

Implemented environment precedence, ignored-document filtering, exact skip accounting, hash exports, verified package/image pins, licence checks, validated SBOMs, shared CI setup, telemetry settings and full-history secret scanning.

### Corrective findings

| Finding | Correction | Evidence |
|---|---|---|
| H1 | The actual supply-chain job runs for backend or frontend changes. Failed/missing scope results run a validation step that fails closed. | [before](evidence/rework-controls-red.txt), [focused suite](evidence/rework-focused.txt) |
| M1 | Independently enumerate installed production identities from lock locations and installed manifests. Reconcile exact names/versions; reject empty, incomplete and extra metadata. Explicitly exclude absent optional packages and the private root; collect omitted installed optional artifacts with the pinned checker. | [CLI regressions](evidence/rework-focused.txt), [real collection](evidence/rework-npm-collection.txt), [real policy failure](evidence/rework-npm-real.txt) |
| M2 | Parse Compose/workflow image values and Dockerfile FROM tokens. Comments cannot satisfy the digest check. Cover quoted values, malformed digests and multiline non-FROM instructions. | [regressions](evidence/rework-focused.txt), [current references](evidence/rework-pins-check.txt) |
| M3 | Run eligible controls independently, retain per-check logs/statuses, fail their aggregate, and upload generated SBOMs/logs after a sibling failure. No continue-on-error. The bounded execution test seeds a licence failure and verifies later SBOM/image execution and upload eligibility. | [execution regression](evidence/rework-focused.txt), [live run](evidence/rework-independent.txt) |

The two additional npm-name cases also fail before their fix: [captured failures](evidence/rework-npm-name-red.txt). npm names now remain exact rather than using Python normalization. The 33 control cases fail against the preserved pre-fix scratch tree (20 failed, 13 passed). The complete focused run passed 59 cases. The final post-Certifi recheck passed all 50 control/licence/MCP cases; the other nine CI environment cases also pass in the full 817-case unit tier. [Final focused recheck](evidence/rework-final-focused.txt), [final unit tier](evidence/rework-final-unit.txt). The Architect's original [review](qa-review.md), [handoff](architect-handoff.md) and before-fix probes remain unchanged.

### MCP 2.2 compatibility

Recorded the selected bounded amendment in requirements, blueprint and brief before editing `api/mcp/`. MCP and mcp-types are now **2.2.0**; the earlier 2.0 freeze is superseded. SDK registration translates only known gateway denials to expected tool/resource errors, using catalogued reason codes. Unexpected failures remain unexpected for SDK masking, with sanitized causes and no raw provider-exception logging. Route shapes, schemas, gateway enforcement and input-guardrail JSON stay unchanged.

All five compatibility regressions fail on the preserved implementation and pass after the fix, including sentinel exception text in tool/resource responses and application logs. The original three policy-denial/concurrent-reply cases pass unchanged. [Before](evidence/rework-mcp-red.txt), [focused results](evidence/rework-focused.txt), [original cases](evidence/rework-mcp-original.txt), [exact lock delta](evidence/rework-lock-diff.txt), [exports](evidence/rework-exports.txt), [MCP wheel](evidence/rework-mcp-wheel.txt), [types wheel](evidence/rework-mcp-types-wheel.txt).

### Remaining policy and image blockers

The real gates still reject NumPy's CC0 term, caniuse-lite's CC-BY-4.0 and GSAP's custom terms. Metadata corrections remain exact-version and OSI-only. The exact NumPy wheel includes Highway's CC0 notice; deleting that term is not a metadata correction. [current Python gate](evidence/rework-final-licence.txt), [npm result](evidence/rework-npm-real.txt), [NumPy artifact](evidence/rework-numpy-wheel.txt), [bounded UI migration and owner choice](licence-remediation.md). No UI source or dependency file changed.

Four existing image failures remain unaccepted. Prometheus is resolved with the newly published security release, after verifying the exact image, Apache notices, maintainer changelog, existing configuration and isolated old-WAL replay/query. [Release](evidence/rework-prometheus-release.txt), [clean scan](evidence/rework-prometheus-new-candidate.txt), [compatibility smoke](evidence/rework-prometheus-data-compat.txt), [36 existing tests](evidence/rework-prometheus-pin-tests.txt), [Compose](evidence/rework-prometheus-compose.txt). No existing metrics volume was mounted; profile, ports and volume names stay unchanged. The complete backend tier preceded this compose-only pin update; its source/dependencies are unchanged.

The verified Grafana 13.2.4 candidate also fails the critical gate, so it is not substituted into compose. [Candidate scan](evidence/rework-grafana-candidate-scan.txt), [registry metadata](evidence/rework-image-candidates.txt), [compatible artifact requirements](image-remediation.md).

The independent runner completed with aggregate exit 1 before the later image fixes; final individual results supersede its application, Ollama and Prometheus entries explicitly. Its host Ollama attempt timed out; the same verified scanner/database then completed inside Docker with exit 2. All seven final images have completed individual results: application, Redis and the verified Prometheus 3.15.1 security replacement pass; Grafana, Ollama, pgvector and Redpanda fail. [Final results](evidence/rework-final-image-results.txt), [full runner statuses](evidence/rework-independent/results.tsv), [Ollama completion](evidence/rework-ollama-local-complete.txt). Scanner download connectivity failed in that attempt; image execution continued with the previously checksum-verified same-version tools already on PATH. No advisory ignore was added.

Fresh advisory data also rejected Certifi 2026.6.17; the verified MPL-2.0 wheel at 2026.10.19 uses the security-age exception. Only Certifi changed in that lock operation, and the rebuilt application passes. [Wheel/source](evidence/rework-certifi-wheel.txt), [lock delta](evidence/rework-certifi-lock-diff.txt), [fresh exports](evidence/rework-certifi-exports.txt), [application scan](evidence/rework-certifi-image.txt).

LiteLLM remains **1.103.2**, unchanged. Its locked core wheel is MIT. The primary-source incident check found no affected version in the inspected local lock history; that scoped conclusion does not cover unrecorded installations. [Licence/incident result](evidence/litellm-check.md).

## Acceptance

| Check | Status | Evidence |
|---|---|---|
| A1 | Backend passes; blocked by real licence/image gates | [unit](evidence/rework-final-unit.txt), [integration](evidence/rework-int-e2e.txt), [focused](evidence/rework-focused.txt) |
| A2 | Pass | [mode](evidence/config-mode.txt) |
| A3 | Pass | [ignored docs](evidence/docs-links.txt) |
| A4 | Control corrections pass; real dependency policy remains blocked | [Python](evidence/rework-final-licence.txt), [seeded rejection](evidence/rework-final-licence-fixture.txt), [npm](evidence/rework-npm-real.txt) |
| A5 | Strict schema validation passes; independent upload path corrected | [fresh SBOMs and hashes](evidence/rework-final-sbom.txt), [execution regression](evidence/rework-focused.txt) |
| A6 | Secret scan passes; image gate blocked | [secrets](evidence/rework-gitleaks.txt), [live independent run](evidence/rework-independent.txt), [completed final image results](evidence/rework-final-image-results.txt) |
| A7 | Pass: parsed digests, Poetry 2.3.3 and MCP 2.2.0; recorded security-age exceptions | [pins](evidence/pins.txt), [current check](evidence/rework-final-pins.txt), [lock](evidence/rework-lock-diff.txt) |
| A8 | Pass: scoped LiteLLM result accepted in review | [result](evidence/litellm-check.md), [review](qa-review.md) |
| B1 | Not started: part-a gate | [build log](build-log.md) |
| B2 | Not started: part-a gate | [build log](build-log.md) |
| B3 | Not started: part-a gate | [build log](build-log.md) |
| B4 | Not started: part-a gate | [build log](build-log.md) |
| B5 | Not started: part-a gate | [build log](build-log.md) |
| B6 | Not started: part-a gate | [build log](build-log.md) |
| B7 | Not started: part-a gate | [build log](build-log.md) |
| B8 | Not started: part-a gate | [build log](build-log.md) |
| A-sec | Part-a regressions pass; part-b threats pending | [focused regressions](evidence/rework-focused.txt), [original threat cases](evidence/threat-tests.txt) |
| A-mem | Four part-b service measurements pending | [build log](build-log.md) |

## Test counts

The historical pack records 1568 backend passes and 10 skips. Actual pre-change collection was **1591**: 878 passed, 3 failed, 710 service-related skips. That is 13 pre-existing cases above the historical snapshot. [Baseline](evidence/baseline-pytest.txt), [JUnit](evidence/baseline-pytest.xml).

Initial part a added 27 cases and passed **1608 backend cases** (777 unit, 831 integration/e2e), with the original 10 live-MinIO skips. Corrective work adds **40 cases**: 33 executable control cases, 5 MCP cases and 2 npm exception-name cases. Final corrective result: **1648 backend passed** (817 unit, 831 integration/e2e), with exactly **10 original live-MinIO skips**. The skip guard passes. Final collection is **1658**, exactly 67 additions over the observed 1591 baseline (27 initial part-a cases plus 40 corrective cases), with no removed baseline case. Two existing console parametrizations generate a fresh UUID at collection; the identity audit normalizes only those UUIDs, after verifying their source. [Count audit](evidence/rework-final-counts.txt), [full tier](evidence/rework-int-e2e.txt), [skip guard](evidence/rework-skips.txt). [Final unit](evidence/rework-final-unit.txt), [focused JUnit](evidence/rework-focused.xml).

Vitest **207** and Playwright **82** passed in the earlier part-a verification; they were not repeated in this corrective pass because UI source/dependencies are unchanged. [UI checks](evidence/ui-checks-a.txt), [browser run](evidence/playwright-a.txt). No browser installation command ran. Part b adds zero cases because it has not started. No test was weakened, deleted or given a new skip.

## Migrations, memory and deviations

Migrations: **none**. Existing setup reached `0010`; no schema or HTTP/OpenAPI change. The selected MCP source amendment is the only API-source exception. The first isolated-store attempt was unavailable and retained separately; stores were started without touching unrelated services, and the original three MCP cases then executed and passed.

No Valkey, Kafka, SeaweedFS or Ollama service memory measurements are claimed. Image inspection does not satisfy A-mem.

The export plugin has no `--with-hashes` flag; supported exports contain validated hashes. The reusable threat template is kept inside Sprint 011, with that location reconciled in the pack. No other sprint folder changed. The earlier reviewed gitleaks fingerprints are retained. Browser-runtime isolation and prior security pin exceptions remain documented in the build log and pins.

The live corrective run caught a non-FROM Dockerfile parsing defect and outdated MCP/Certifi classifier corrections. These were fixed with fresh passing pin and wheel/licence evidence; the earlier failed check output remains preserved. Generated check statuses are not relabelled. The first complete integration attempt exposed a fixed-window clock assumption and a worker startup deadline miss under host load. Freeze only the sign-in test's route-module clock, preserving every request/assertion; the worker test stays unchanged. Both pass in the [runtime regression](evidence/rework-runtime-regressions-local.txt). The final full tier uses the pinned Python image, the locked environment and loopback-only proxies to the isolated stores; its network guard remains unchanged. [Reproducible environment](evidence/rework-runtime-environment.txt), [preserved earlier failures](evidence/rework-int-e2e-before-final.txt).

## Verification

Final lint and typecheck pass. Hash exports match the lock, the DDL guard passes, and both generated SBOMs pass strict CycloneDX 1.6 validation (225 Python and 668 npm components), including Certifi 2026.10.19. The seeded non-OSI fixture rejects BUSL as required. [Lint](evidence/rework-final-lint.txt), [mypy](evidence/rework-final-mypy.txt), [exports](evidence/rework-final-exports.txt), [DDL](evidence/rework-final-ddl.txt), [SBOMs](evidence/rework-final-sbom.txt), [fixture](evidence/rework-final-licence-fixture.txt), [documentation links](evidence/rework-final-doc-links.txt), [generated documentation](evidence/rework-final-generated-docs.txt), [scope and source hashes](evidence/rework-source-scope.txt).

## Open questions

- Select a compliant NumPy artifact/dependency strategy or explicitly amend the licence policy; the Builder has not approved CC0.
- Select the proposed bounded UI dependency migration before changing the UI; the current scope still prohibits that work.
- Establish compatible fixed artifacts for the four failing upstream images. The verified Grafana candidate also fails; no unverified digest or advisory exemption is accepted.
- The fresh scanner installer could not reach upstream release assets locally. Completed scans used the previously checksum-verified exact tools. This connectivity limit is recorded separately from security results.

Details: [licence proposal](licence-remediation.md), [image requirements](image-remediation.md), [questions](../../QUESTIONS.md). Part b and its preflight/live-service/memory checks remain unstarted under the explicit part-a-green rule. No Sprint 012 work was started.

## Proposed commit blocks

Human review only; no commands below were executed. Preserve the pre-existing builder-brief hunk when selecting the new amendment.

```bash
git add -p planning/sprints/011-baseline-and-stack/requirements.md planning/sprints/011-baseline-and-stack/blueprint.md planning/sprints/011-baseline-and-stack/builder-brief.md
git commit -m "docs(planning): bound MCP compatibility and template scope"

git add core/settings.py scripts/docs/check_links.py scripts/check_skips.py api/mcp/server.py api/mcp/tools.py api/mcp/resources.py
git commit -m "fix(core): preserve environment precedence and controlled MCP denials"

git add tests/unit/test_config_mode.py tests/unit/test_docs_links.py tests/unit/test_check_skips.py tests/unit/test_ci_env.py tests/unit/test_licence_gate.py tests/unit/test_supply_chain_controls.py tests/unit/test_mcp_compat.py tests/unit/test_observability_profile.py tests/e2e/test_tenancy.py tests/e2e/test_web_edge.py tests/fixtures/licence/ tests/skip_allowlist.json
git commit -m "test(ci): cover complete inventories and independent failing controls"

git add .github/ .dockerignore .gitignore .gitleaksignore Dockerfile docker-compose.yml pyproject.toml poetry.lock requirements/ scripts/supply_chain/ scripts/ci/ scripts/setup_db.sh
git commit -m "ci(ops): enforce pinned dependencies and independent supply-chain gates"

git add AGENTS.md CODEX.md CONTRIBUTING.md
git commit -m "docs(ops): document inventory and dependency verification"

git add planning/COMMIT_PLAN.md planning/history/COMMIT_PLAN.md planning/STATE.md planning/QUESTIONS.md planning/program/README.md planning/sprints/011-baseline-and-stack/acceptance.md planning/sprints/011-baseline-and-stack/build-log.md planning/sprints/011-baseline-and-stack/report.md planning/sprints/011-baseline-and-stack/threat-model-template.md planning/sprints/011-baseline-and-stack/licence-remediation.md planning/sprints/011-baseline-and-stack/image-remediation.md planning/sprints/011-baseline-and-stack/qa-review.md planning/sprints/011-baseline-and-stack/architect-handoff.md planning/sprints/011-baseline-and-stack/evidence/ CHANGELOG.md
git commit -m "docs(planning): record corrective evidence and remaining blockers"
```
