# Sprint 045: Blueprint
- **Contract:** `GET /v1/system/modules` (from 013) gains `installed: bool` and `version: str|null` per module, read from package metadata. OpenAPI snapshot refreshed. No other route changes.
- **Distributions** (names are functional; the Builder records the final layout in `build-log.md`):
  | Wheel | Packages | Entry point in `platform.modules` |
  |---|---|---|
  | `gap-kernel` | `core`, `ports`, `adapters`, `workers`, `config`, `api` shell | `kernel` |
  | `gap-gateway` | `gateway`, `evidence` core | `gateway` |
  | `gap-evidence` | `evidence` M2 extensions | `evidence` |
  | `gap-agents` | `api/agent`, `api/mcp`, `sandbox_agent`, `runtime` | `agents` |
  | `gap-dataplane` | `dataplane` | `data` |
  | `gap-lineage` | `lineage` | `lineage` |
  | `gap-insights` | `insights` | `insights` |
  - Each entry point returns the module's registration (routes, workers, nav, migrations it needs).
  - Startup: an enabled module that is not installed fails with a clear error. An installed module that is not enabled stays off and answers `module_disabled`.
  - `scripts/release/build_wheels.sh` builds all wheels into `dist/` with Poetry 2.3.3 and writes `dist/SHA256SUMS`.
- **Editions** (`editions/<name>.toml`: wheels, `ENABLED_MODULES`, compose profiles):
  | Edition | Wheels | Profiles |
  |---|---|---|
  | Gateway | kernel, gateway | core |
  | Assurance | + evidence | core, trust |
  | Agents | + agents | core, models |
  | Data | + dataplane, lineage, insights | core, lake (models, cdc and mail optional) |
  | Full | all | as the task needs; never all at once inside the 12 GB WSL limit |
  - The `models` profile is optional for Data. Without it, dashboards, reports, alerts and pipelines work. Ask-your-data and the document agent answer with the model port's existing unavailable error.
  - `compose/editions/<name>.yml` overrides set `ENABLED_MODULES` and the image build arg `EDITION`. The Dockerfile installs only that edition's wheels with `pip install --no-index --find-links dist`.
  - `scripts/release/install_edition.sh <edition>`: a fresh venv in a temp dir, install from `dist/` only, run migrations, boot, run the edition's smoke set (the `edition_smoke` tests that `scripts/ci/edition_smoke.sh` runs from source).
- **Data:** no migration. Migrations stay in one Alembic tree; each module lists the revisions it needs, and the smoke set checks the head. For example, the evidence module lists the Sprint 042 revision that adds `ai_systems` and `evidence_packs`, and the Sprint 043 revision that adds `system_assessments`.
- **Supply chain:** `scripts/supply_chain/sbom.sh` (Sprint 011) gains a release mode, `scripts/supply_chain/sbom.sh --release`. It runs `cyclonedx-py` per wheel set, `cyclonedx-npm` for `ui/`, the image SBOM tool from Sprint 011 per pinned image, and the ML-BOM generator from Sprint 043; then merges into `release-sbom.cdx.json`. `scripts/release/licence_report.py` writes `licence-report.md` (component, version, licence, edition, default or optional). It uses the same allow list as the licence gate `scripts/supply_chain/licence_gate.sh` (Sprint 011), which still runs, and fails on a non-OSI licence in a default profile. Grafana (AGPL-3.0, optional profile, unmodified) is listed as such.
- **Release gate:** `.github/workflows/release.yml` on a `v*` tag: build wheels, edition matrix from wheels, SBOM, licence report, image scan. Artifacts attached only when all pass. CI on pull requests keeps `.github/workflows/editions.yml` from Sprint 013, which calls `scripts/ci/edition_smoke.sh`.
- **Runbooks:** `docs/runbooks/upgrade.md` and `docs/runbooks/backup-restore.md`, linked from `docs/operations.md`.
  - Upgrade covers: backup first; DuckDB and DuckLake extension bump and catalog migration; a protected snapshot still readable and its receipt still replays; Postgres 16 to the next major with `pg_dump`/`pg_restore` (pgvector, roles, `gap_app` grants, RLS checked after); digest bumps with `models.lock` and `evidence/pins.txt`.
  - Backup covers: `pg_dump` of the platform and `lakehouse` databases, the object store buckets, the receipt, checkpoint and TSA keys (stored apart from data), and the log tables.
  - `scripts/verify/restore.sh`: back up, restore into a separate compose project with new volumes, then verify the chain, one receipt, one evidence pack for an `ai_systems` row (Sprint 042), a log consistency proof against a checkpoint saved before the backup, and one lakehouse read at a pinned snapshot.
- **Gateway, events, UI:** none, except the modules list showing the version.
- **Tests:** wheel content test (each wheel's RECORD holds only its packages); entry point discovery test; enabled-not-installed start failure; installed-not-enabled gives `module_disabled`; `test_data_edition_without_models` (Data boots with `core, lake` only and a dashboard renders); licence report fails on a seeded non-OSI fixture; SBOM includes models with digests; restore drill.
- **Docs:** `docs/deployment.md` "Editions"; `docs/getting-started.md` names the edition; ADR-0013 section on packaging; `CONTRIBUTING.md` release steps.
