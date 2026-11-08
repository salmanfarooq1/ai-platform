# Contributing

For anyone who changes the code or the docs. It covers branches and commits, tests, the checks to run, and which docs to update with a change. Local setup is in [docs/getting-started.md](docs/getting-started.md).

## Branches and commits
- **Branches.** Work happens on a branch named `sprint/NNN-slug`, created from the branch it builds on. Nothing is committed directly to `main`.
- **Commit messages** follow Conventional Commits with a scope: `type(scope): summary`. Types are `feat`, `fix`, `refactor`, `test`, `docs` and `chore`. Scopes are `api`, `ui`, `core`, `jobs`, `trust`, `sandbox`, `events`, `adr`, `design`, `planning` and `docs`.
- **Grouping.** Group commits by area (code, tests, UI, docs), not as one large commit.
- **Pull requests** use `.github/pull_request_template.md`.

## Tests
- **Coverage.** New behaviour needs a test, and a bug fix needs a regression test that fails without the fix.
- **Tiers** are pytest markers:
  - `unit`: isolated, no services
  - `integration`: real Postgres and Valkey
  - `e2e`: the full app over HTTP
  - `tests/contracts/`: one suite per port, run against every adapter of that port
- **No real providers.** Models and embeddings are always fakes in tests, and the network is blocked.
- **Skips.** Only entries in `tests/skip_allowlist.json` may skip. `scripts/check_skips.py` requires each entry's exact count, class, name and reason. A check that needs a live external service belongs in `scripts/verify/`, not in a skipped test.
- **Never** weaken, skip or delete a test to make a change pass.
- **UI.** Vitest covers components, and Playwright covers flows against a real API with fake models. Axe checks accessibility in both themes.

## Checks before a pull request

```bash
poetry run ruff check api core gateway ports adapters workers sandbox_agent tests scripts/e2e scripts/verify scripts/eval scripts/docs
poetry run mypy
bash scripts/check_no_ddl.sh
poetry run pytest -q --junitxml=pytest-results.xml
poetry run python scripts/check_skips.py pytest-results.xml
poetry run python scripts/docs/generate.py --check
cd ui && npm run tokens:check && npm run lint && npx tsc --noEmit && npm test -- --run && npm run build && npx playwright test
```

CI runs the same checks, plus the eval gate and a migration check on an empty database.

## Supply chain

Use Poetry 2.3.3 with `poetry-plugin-export==1.10.1`, and install the tools with `poetry install --with dev,supply-chain`. Node 24 is required by the pinned npm licence checker.

```bash
scripts/supply_chain/export_locks.sh --check
scripts/supply_chain/licence_gate.sh
scripts/supply_chain/sbom.sh
scripts/supply_chain/install_scanners.sh /tmp/platform-scanners
PATH=/tmp/platform-scanners:$PATH python scripts/supply_chain/check_secret_controls.py
PATH=/tmp/platform-scanners:$PATH gitleaks git --redact --no-banner .
PATH=/tmp/platform-scanners:$PATH scripts/supply_chain/image_scan.sh
```

The secret scan retains every default detector. `.gitleaks.toml` restricts metadata exceptions to exact reviewed public checksum values or literal variable names in named evidence files. `check_secret_controls.py` proves adjacent credentials, unreviewed values and matching values outside approved paths still fail, and a separate default credential detector remains active. Existing history fingerprints remain in `.gitleaksignore`.

Exports retain SHA-256 hashes; regenerate them after an intended lock change with `scripts/supply_chain/export_locks.sh`. The export plugin includes hashes by default. SBOMs are validated CycloneDX JSON under the ignored `sbom/` directory and uploaded together in CI.

The gate checks installed main-group Python packages and production npm dependencies against `scripts/supply_chain/osi-licences.txt`. The private first-party UI root is excluded by exact name and version. A licence metadata exception needs the exact package version, an OSI SPDX expression, the release source checked and a reason in `scripts/supply_chain/licence-exceptions.txt`. Review the release's licence text before adding an exception. Non-OSI licences cannot be exempted. Image exceptions belong in `scripts/supply_chain/grype.yaml`, with a finding, package and review reason.

Artifact-specific corrections must prove which code ships, retain the publisher's original notices, and bind to the exact wheel hash, interpreter/platform and installed member hashes. The audited NumPy Linux CPython 3.11 correction is in `scripts/supply_chain/artifact_licences.py` and its immutable member manifest; another wheel or platform fails closed pending its own audit. Only explicitly reviewed complete `WITH` expressions are permitted. npm corrections use the `npm:` prefix and exact package names/versions. Fonts are checked-in audited OFL assets; the landing motion uses browser primitives.

Image scans include every optional profile and build-only service. Each security recipe pins external bases by digest and source/package inputs by hash. The gate captures final image IDs and CycloneDX reports in the generated image-report directory shown below, scans those immutable IDs, and continues other image checks if one build or scan fails.

Generated output (created by the scanner):

```text
sbom/checks/images/
```

## Docs in step with the code

| If you change | Also update |
|---|---|
| A setting | Its `description` in `core/settings.py`, then run `scripts/docs/generate.py` |
| A route or a response | `poetry run python scripts/update_openapi.py`, then `npm run gen:api` in `ui/`, and the route table in [docs/api/README.md](docs/api/README.md) |
| A reason code or event type | `gateway/reasons.py` or `ports/events.py`, then `scripts/docs/generate.py` |
| The schema | A new migration, and the migration table in [docs/deployment.md](docs/deployment.md#migrations) |
| How the system works | [docs/architecture.md](docs/architecture.md) |
| A cross-cutting decision | A new ADR in `docs/adr/`. To change a decision, write a new ADR and mark the old one superseded |
| Running or operating it | [docs/operations.md](docs/operations.md) or [docs/deployment.md](docs/deployment.md) |
| Anything users notice | [CHANGELOG.md](CHANGELOG.md), under Unreleased |
| The UI | `docs/design/` and the design skill rules |

Tests fail when a generated reference table is out of date or when a doc links to a file that does not exist.

## Writing docs
- **Tense.** Present tense: say what the system does.
- **Content.** No build history, sprint numbers or to-do lists in product docs. Planning lives in `planning/`.
- **One place.** Each topic lives in one file, and other files link to it.
- **Sentences.** Short and simple. Name things the way a reader knows them.
- **Accuracy.** Run every command you document.

After prerequisite installation, CI runs `scripts/supply_chain/run_checks.sh` for backend or UI changes. Missing change-scope outputs fail the required job. Each independent check writes a log and exit status under `sbom/checks/`; the aggregate fails if any check fails. Generated SBOMs and check logs are uploaded even after a sibling failure.

npm metadata must match the installed production identities derived independently from lock locations and package manifests. Missing, extra and version-mismatched entries fail. Absent optional packages are counted separately; installed optional artifacts remain required. The pinned collector is queried per artifact when its production traversal omits an installed optional peer. Only the private first-party root is excluded.
