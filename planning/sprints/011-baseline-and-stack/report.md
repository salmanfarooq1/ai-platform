# Sprint 011 implementation report

Status: accepted for local successor implementation by the Architect. All final local acceptance checks pass; required remote CI remains a pending human landing gate. Historical failed evidence remains unchanged. The earlier part-a report is preserved in `report-part-a-history.md`.

## Result

The default stack is Postgres 16 with pgvector, Valkey Search and the worker. Apache Kafka (`streams`), SeaweedFS (`lake`), local models (`models`) and observability remain optional. Outbox delivery remains the default. Every published service port binds to loopback.

The supply-chain gate parses actual image references, validates complete Python/npm licence inventories, generates validated SBOMs and runs independent checks even after a sibling fails. Frontend dependency changes also run that gate. Security services use reviewed recipes with pinned bases, exact source/package hashes, frozen Go inputs and retained notices. Both runtime and init services select those recipes; scans target the captured immutable output IDs. No advisory ignore or licence-policy relaxation was added.

NumPy's exact CPython 3.11 Linux x86_64 artifact audit supports an artifact-specific metadata correction, guarded by wheel and installed-member identities. It is not a version-wide waiver or an upstream reproducible-build attestation. The source/compiler/member/symbol evidence and original notices remain. The UI serves the original Geist font assets with OFL notices and uses browser-native landing motion; reduced motion, scroll progression and lazy bundle isolation remain tested. MCP 2.2 translates controlled gateway denials and masks unexpected exceptions.

Existing Postgres and Grafana stores require the documented backup/clone or logical restore into new volumes. The old volumes remain untouched. Ollama similarly uses a new volume, disables cloud inference and pruning, and retains original model data for operator-controlled migration. No existing customer volume was attached to a new image.

## Current verification

| Check | Captured result | Evidence |
|---|---|---|
| Final unit tier | 884 passed, 845 deselected, no skips | `evidence/architect-final-unit.txt`, `architect-final-unit.xml` |
| Independent final control review | 87 passed | `evidence/architect-final-controls.txt`, `.xml` |
| Full backend integration/e2e | 835 passed, exactly 10 allowed skips; complete tier exits 0 | `evidence/finish-integration-final.txt`, `.xml`, `finish-integration-final-skips.txt` |
| UI unit and build checks | 207 Vitest passed; lint, tokens, typecheck, build, chunk/copy guards passed | `evidence/autonomous-ui-vitest-bounded.txt`, `autonomous-ui-lint.txt`, `autonomous-ui-build-checks.txt` |
| Browser tier | 82 passed, complete real-API suite exits 0; accessibility, responsive and reduced-motion journeys included | `evidence/architect-final-browser-green.txt` |
| Exact tooling/exports | Poetry 2.3.3, export 1.10.1; lock and 131 main / 166 dev hash exports pass; MCP 2.2.0 | `evidence/finish-records-lock-export.txt` |
| Licence | Full OSI gate passes; seeded BUSL fixture rejected | `evidence/architect-real-licence.txt`, `architect-non-osi-fixture.txt`, `architect-numpy-audit.txt` |
| Dependency SBOM | Strict CycloneDX 1.6 validation; Python 225, npm 651 components; hashes captured | `evidence/finish-records-sbom.txt`, `finish-records-sbom-hashes.txt` |
| Secrets | Full-history scan clean, 161 commits; final filesystem metadata scan and seeded anti-suppression checks pass | `evidence/architect-final-history-secrets.txt`, `architect-final-snapshot-secrets-reviewed.txt`, `architect-secret-controls.txt`, `architect-secret-metadata-review.json` |
| Final image gate | Common runner exits 0; all 12 immutable outputs pass; exact runtime layers/config match live-verified artifacts | `evidence/architect-consolidated-images.txt`, `architect-consolidated-image-results.json`, `architect-consolidated-image-artifacts/`, `architect-artifact-runtime-binding.json` |
| Pin inputs and age | Parsed refs pass; exact security-build inputs and primary-source age review recorded | `evidence/finish-records-docs-pins.txt`, `finish-records-pins-inputs.txt`, `pins.txt`, `architect-go-module-dates.json` |
| Valkey | 34 live cache/control cases; metadata-outage regression and shared governance outage pass | `evidence/stack-cache-valkey-final.txt`, `stack-cache-error-recheck.txt`, `stack-governance-outage.txt` |
| Kafka | 21 live contract/flow cases; topics, partitions and retention verified | `evidence/stack-kafka-final-live.txt` |
| SeaweedFS | 10 live object contracts; signed PUT/GET; changed-key and expired GET denied 403 | `evidence/stack-seaweedfs-final-runtime.txt`, `stack-seaweed-presign-negative.txt` |
| Compose and preflight | Profiles render, loopback ports, digest-pinned upstream profile images, positive and failure checks pass | `evidence/stack-compose-final-redacted.txt`, `stack-compose-security-build-test.txt`, `stack-preflight-final-recheck.txt`, `stack-preflight-bad-engine-final.txt` |
| Runtime memory | Valkey 14.18 MiB, Kafka 473.9 MiB, SeaweedFS 128.9 MiB after verification; Ollama 103.8 MiB idle without networking | `evidence/stack-memory-final.txt`, `architect-ollama-runtime.txt` |
| Eval | Fixed-12 baseline gate passes, no model provider called | `evidence/architect-final-eval.txt` |
| Static/docs | Ruff/mypy/DDL guard pass; generated docs and 35-file link check pass | `evidence/architect-final-lint.txt`, `architect-final-mypy.txt`, `finish-ddl.txt`, `finish-records-docs-pins.txt` |

Final identity reconciliation passes against the observed 1591-case pre-sprint baseline: 1729 collected, 1719 passed, 10 original skips, 138 additions and zero removed baseline cases. Only the generated console-route UUID and the ten explicit MinIO-to-SeaweedFS parameter identities are normalized. Captured output and the audit script are `evidence/architect-final-counts.txt` and `architect-final-count-audit.py`. Runtime/shared fixtures/selected integration sources (244 files) and browser inputs (305 files) match their isolated runners byte for byte (`architect-final-runner-source-binding.json`); all 884 unit cases run directly in the final source tree.

## Limits and transitions

The supplemental final filesystem scan flagged 189 metadata matches: 63 exact public NumPy member checksums, 112 literal environment-variable names in skip reasons, five rendered public-prefix/numeric examples, one OpenAPI checksum and eight already reviewed historical findings. All are triaged in a file-hash-bound metadata inventory. New `.gitleaks.toml` exceptions retain every default detector and combine exact path with exact public values/names for `generic-api-key` only. CI runs the actual seeded anti-suppression regression before the full-history scan. The historical eight commit fingerprints are unchanged; the supplemental filesystem scan uses their equivalent path/line fingerprints. No real credential exception or whole-file exclusion was added. The first captured snapshot is preserved as review inventory; v3 includes the final CI/configuration correction.

Fixed-critical scans do not imply an absence of lower-severity or unfixed findings. Exact artifacts and advisory database identity are recorded. Local scanner download connectivity failed in earlier attempts; verified cached binaries completed actual scans. This does not claim an executed remote CI workflow.

Live storage and Kafka proofs use one local node. They do not establish production authentication, multi-broker operation or every deployment's data migration. Ollama's isolated startup proof makes no inference, GPU or loaded-model memory claim; model locks and those checks belong to 013. Service upgrade steps are in `docs/postgres-upgrade.md`, `docs/grafana-upgrade.md` and `docs/ollama-upgrade.md`.

The first concurrent validation layout shared cache keys between integration fixtures and browser sessions. Its failed evidence is preserved. The browser suite now has a separate final-image Valkey instance. A later sandbox timeline request exceeded its unchanged assertion deadline under concurrent validation; its failed evidence remains. The separate-cache final browser tier now passes all 82 cases. The complete backend tier subsequently passes without changed product code, assertions or deadlines.

The WSL host also exhibits real backward wall-clock steps. Bounded clock-source/time-sync diagnostics did not establish a fix; original `tsc` and active time synchronization were restored. No restart or persistent runtime change was made. This is documented in `planning/QUESTIONS.md`; acquiring the chain lock does not make wall time monotonic. Historical signed timestamps remain untouched. Both full final regression tiers pass without a deadline/assertion change.

No schema migration, commit, push, merge, registry publication or paid resource was used. Sprint 012 product implementation has not begun. Architect preparation in 012, 013, 014, 015 and the 022 lineage prerequisite is separate planning work under the owner's autonomous-delivery instruction.

## Commit groups

Seven commits, made only after the owner's go. Path rules assign every changed path to exactly one group (660 paths, none unassigned). The owner's own untracked root files and the local security-skill links are never staged.

| # | Commit | Paths |
|---|---|---|
| 1 | `fix(core): preserve controlled failures and Valkey compatibility` | `core/settings.py`, `api/mcp/`, the Valkey and knowledge adapters, the retriever, the skip and link checks |
| 2 | `fix(ui): serve audited fonts and keep native landing motion` | `ui/`, `docs/design/`, the governed-design skill |
| 3 | `ci(ops): gate pinned dependencies and final service artifacts` | `.github/`, dotfiles, Dockerfile, compose, `docker/`, lock files, `requirements/`, supply-chain and verify scripts |
| 4 | `test(ops): keep baseline contracts and cover supply-chain failures` | `tests/` |
| 5 | `docs(planning): add the sprint 011 acceptance evidence` | `planning/sprints/011-baseline-and-stack/evidence/` |
| 6 | `docs(planning): record the verified stack and the sprint 011 acceptance` | root guides, `docs/`, `planning/` top level, `history/`, `program/`, this sprint folder |
| 7 | `docs(planning): add the sprint 012 to 032 plans` | `planning/sprints/012-*` to `032-*` |

The accepted prerequisite is preserved outside the repo at `/home/ubuntu/ai-platform-snapshots/011-accepted-v3`, with a hash manifest and explicit exclusions/deletions. Sprint 012 uses `/home/ubuntu/ai-platform-sprints/012-pillars-and-boundaries` on its own branch.

Later local sprints use isolated worktrees plus accepted prerequisite snapshots and per-sprint delta manifests under `planning/program/branching-and-commits.md`. A human reconciles and lands them in order. No model-authored commit or merge is needed for local continuation.
