# Branching, commits and releases

No model runs `git commit`, `git push` or `git merge`. Models write the proposed commands in `report.md`. A human runs them.

## What happened before (and why this changes)
Sprints 005 to 010 were built in one working tree, saved as git tree objects (`COMMIT_PLAN.md`), stacked on sprint branches, and landed together in one pull request. That worked once, but it hid each sprint's diff and depended on tree ids that live in one machine's `.git`. Program 2 moves to one branch and one pull request per sprint. Sprint 011 moves `COMMIT_PLAN.md` to `planning/history/`.

## Branches
| Branch | Purpose | From | Into |
|---|---|---|---|
| `main` | Always green. Only merged pull requests. | — | — |
| `planning/sprint-plans` | The plan and the sprint packs | `main` | `main`, before Sprint 011 starts |
| `sprint/NNN-slug` | One sprint, for example `sprint/021-data-access-and-federation` | `main`, after the previous sprint merged | `main` |
| `fix/NNN-short-name` | A QA fix after a sprint merged | `main` | `main` |
| `spike/NNN-topic` | Throwaway experiments named in a blueprint (for example the MetricFlow spike) | sprint branch | never merged; results go into the sprint's evidence |

Rules:
- One sprint, one branch, one pull request. Do not stack an unmerged sprint on another.
- Start a sprint branch only when `main` is green and the previous sprint is merged.
- Rebase on `main` before opening the pull request. No merge commits inside a sprint branch.
- Merge with a merge commit, so each sprint keeps its commit blocks. Delete the branch after merge.
- The plan branch PR excludes stray untracked files at the repo root (old plan files from the abandoned deploy branch).

### Autonomous local implementation before human landing
The owner's autonomous-delivery instruction permits an isolated local worktree per sprint after the previous sprint's evidence is accepted, while its human commits are pending. Preserve the accepted prerequisite filesystem snapshot and a per-sprint change manifest; copy only reviewed source/planning inputs, excluding secrets, generated dependency trees and unrelated root files. Each worktree uses its own `sprint/NNN-slug` branch. This is an exception to the previous-merge prerequisite for local implementation only. It creates no model-authored commits or merges. Reports identify the prerequisite snapshot and give the human the reconciliation and commit steps for sequential landing. Pull requests, rebases, merges and release tags retain the normal human workflow above.

Local acceptance requires captured passing checks on that exact source snapshot and validation of the CI configuration that runs those checks. It never asserts a remote workflow ran on uncommitted files. Required remote CI on the human-committed diff remains a separate human landing gate before merge; record it as pending until it actually runs. This separates local successor implementation from landing without deleting, skipping or weakening any test or release check.

## Commit blocks inside a sprint
Use the blocks that apply, in this order. Merge small neighbouring blocks. Past sprints used three to five blocks, which is fine. Each block should pass lint and tests on its own where possible.

| Order | Block | Typical paths | Message type |
|---|---|---|---|
| 1 | Contract | `ports/`, `api/models/`, `docs/api/openapi.json`, `docs/contracts/` | `feat(<scope>)` |
| 2 | Migration | `migrations/versions/` | `feat(db)` |
| 3 | Code | `adapters/`, `core/`, `gateway/`, `evidence/`, `dataplane/`, `lineage/`, `insights/`, `api/`, `workers/` | `feat(<scope>)` |
| 4 | Tests | `tests/` | `test(<scope>)` |
| 5 | UI | `ui/` | `feat(ui)` |
| 6 | Ops | `docker-compose.yml`, `scripts/`, `.github/` | `chore(ops)` or `ci(<scope>)` |
| 7 | Docs | `docs/`, ADRs, `README.md` | `docs(<scope>)`, `docs(adr)` |
| 8 | Planning | `planning/`, `CHANGELOG.md` | `docs(planning)` |

Message format, from `AGENTS.md`: `type(scope): summary`. Lowercase, imperative, no period, no sprint number (the branch carries it).

**One scope list**, kept in `AGENTS.md` (updated in 011): `api`, `ui`, `db`, `core`, `adapters`, `ops`, `ci`, `adr`, `planning`, `gateway`, `evidence`, `agents`, `sandbox`, `events`, `jobs`, `models`, `lake`, `pipelines`, `cdc`, `products`, `quality`, `access`, `lineage`, `semantic`, `insights`, `documents`, `policy`, `approvals`, `identity`, `protocols`, `guardrails`, `memory`, `receipts`, `observability`, `packaging`.

Commits end with the attribution lines the repository owner sets. Model or tool names never appear in files.

## Example: Sprint 021
```bash
git switch main && git pull --ff-only
git switch -c sprint/021-data-access-and-federation
# ... Builder works, QA signs off ...
git add ports/query_engine.py api/models/data.py docs/api/openapi.json
git commit -m "feat(lake): add query engine port and data read contract"
git add migrations/versions/0012_*.py
git commit -m "feat(db): add connection registry and lakehouse tables"
git add dataplane/ adapters/duckdb_engine.py adapters/registry.py core/settings.py gateway/
git commit -m "feat(lake): read client data in place through locked duckdb connections"
git add tests/
git commit -m "test(lake): cover read-only connections and snapshot pinning"
git add docs/ planning/ CHANGELOG.md
git commit -m "docs(adr): record data access adapters"
git push -u origin sprint/021-data-access-and-federation
gh pr create --base main --title "Sprint 021: data access and federation"
```

## Migrations
Numbered in order across sprints. The latest today is `0010`. Each sprint takes the next free number. A sprint that adds none says so in its report. Forward only. The upgrade is tested from the previous head.

## Tags and releases
- Tag `main` after each milestone merges: `v0.15.0` (M0), `v0.20.0` (MG, sellable point), `v0.26.0` (MD), `v0.27.0` (freeze point), `v0.29.0` (MA), `v1.0.0` (ME).
- Each tag gets a `CHANGELOG.md` section with the test delta, migrations, new services and measured memory.

## Pull request checklist (`.github/pull_request_template.md`, extended in 011)
- Acceptance table with evidence links. Threat model signed off.
- Lint, mypy, unit, integration, e2e, UI checks, licence gate, secret scan, edition smoke matrix: all green.
- Test delta against the baseline (1568 backend passed, 10 skipped; 207 Vitest; 82 Playwright at the end of Sprint 010).
- Migrations listed. New SDKs added to the import lint list.
- Docs updated in lockstep: ADR, `docs/`, `STATE.md`, `CHANGELOG.md`.
- Memory measured for any new compose service.
