# Sprint 012 implementation report

Status: Builder evidence is complete except for the Architect-owned Playwright file. The application now has module editions and pillars, decision record version 2, and a single-tenant default with an explicit multi-tenant shape. Migration 0011 adds the record and tenant-shape controls.

## What was built

- **One kernel, three pillars.** The decision record, hash chain and receipts moved from `gateway/` into a separate `evidence/` package. Modules reach the kernel only through `ports/` (bundle, data access, evidence, lineage, errors). import-linter enforces this in CI.
- **Editions.** `ENABLED_MODULES` chooses the modules (`core/modules.py`). A disabled module has no routes and its workers claim no jobs. A call to it is denied with a recorded decision at the module stage of `enforce()`.
- **Decision record version 2.** Version 1 and version 2 records chain together, and receipts still verify offline (`scripts/verify/receipt.py`).
- **Deployment shape.** Single-tenant is the default, and multi-tenant must be declared explicitly. A startup probe checks the shape against the database grants and RLS (`core/identity/deploy_shape.py`).
- **Migration 0011.** Adds record versions, the shape probe and module-filtered job claims. Run it before upgrading the application.
- **UI.** Navigation and the command palette show only the modules the server enabled. A direct link to a disabled module shows "module unavailable".
- **CI.** A per-edition smoke test (`.github/workflows/editions.yml`, `scripts/ci/edition_smoke.sh`) and the import-boundary lint.

## Verification and test delta

| Tier | Sprint 011 | Sprint 012 | Delta |
|---|---:|---:|---:|
| Unit | 902 passed | 990 passed | +88 |
| Integration/e2e | 835 passed, 10 skips | 870 passed, 10 skips | +35 passes, same skips |

The full unit run is Architect-captured in `evidence/unit-architect.txt`. The full live tier, JUnit skip audit, Ruff, mypy, import-linter and UI checks are captured in `evidence/checks.txt`. The ten live skips are the allowlisted SeaweedFS cases. Migration 0011 is required before upgrading the application.

## Acceptance

| Item | Status | Evidence |
|---|---|---|
| A1 | Pass | `evidence/checks.txt` |
| A2 | Pass; tree lint and seeded violations covered | `evidence/import-contracts.txt` |
| A3 | Edition smokes and workflow check pass; Architect container proof captured | `evidence/editions.txt`, `evidence/container-gateway.txt` |
| A4 | Pass; mixed version chain and offline receipt verification | `evidence/record-v2.txt` |
| A5 | Pass; routes, job claiming, denial record and action map | `evidence/module-disabled.txt` |
| A6 | Pass; failed sink write is fail-closed and the real lookup adapter passes its contract | `evidence/sink-fail-closed.txt` |
| A7 | Architect reports 3/3 browser journeys passed; evidence file not present in this worktree | `evidence/playwright.txt` |
| A8 | Pass; API scopes, module metadata, navigation and palette | `evidence/pillars.txt` |
| A9 | Pass; startup, concurrent creation, probe grants and RLS | `evidence/deploy-shape.txt` |
| A-sec | Pass; targeted threat-model tests | `evidence/threat-tests.txt` |

## Deviations and open items

The full unit output was supplied by the Architect because local socket access is blocked in the Builder sandbox. No product code or assertions were changed for WP8. The Architect-owned `evidence/playwright.txt` is not present yet; the Architect verification log records that the three browser journeys passed. `evidence/container-gateway.txt` was supplied by the Architect and was left unchanged. `planning/STATE.md` was not edited; the Architect maintains `planning/MAP.md`.

No open specification questions.

## Commit groups

Seven commits, made only after the owner's go and after the 011 commits. The worktree branch is first moved onto the 011 tip with a mixed reset, which keeps every file, so the remaining diff is 012 only. Path rules assign every 012 path to exactly one group (228 paths, none unassigned). The local `ui/vite.wp6b.config.ts` sandbox workaround and its cache are not committed.

| # | Commit | Paths |
|---|---|---|
| 1 | `feat(gateway): split evidence and ports out of the kernel` | `evidence/`, `ports/`, `gateway/`, `adapters/`, `core/`, migration 0011, run authority |
| 2 | `feat(api): load modules by edition and gate their routes and jobs` | `api/`, `workers/`, admin, verify, e2e and docs scripts |
| 3 | `feat(ui): hide disabled modules and show the server decision` | `ui/` |
| 4 | `ci(editions): smoke each edition and lint import boundaries` | workflows, `scripts/ci/`, Dockerfile, `pyproject.toml`, `poetry.lock` |
| 5 | `test(gateway): cover module boundaries, editions and the evidence split` | `tests/` |
| 6 | `docs(planning): add the sprint 012 acceptance evidence` | this sprint's `evidence/` |
| 7 | `docs(architecture): record module boundaries and the sprint 012 acceptance` | `AGENTS.md`, `CHANGELOG.md`, `docs/`, `planning/` |

