# Sprint 011: Baseline hygiene. Requirements

Infrastructure, Kernel. Planning files, settings, CI and supply chain. No API, schema or UI change.

## Scope
1. Planning drift.
   - `planning/STATE.md`: sprints 000 to 010 are on `main`, and Sprint 010 is QA signed off.
   - Move `planning/COMMIT_PLAN.md` to `planning/history/`.
   - `AGENTS.md`: refresh the stack list (Valkey, Apache Kafka, SeaweedFS, local models through Ollama) and add the commit scope list from `planning/program/branching-and-commits.md`.
   - Fix the links in `planning/program/README.md`.
2. Bugs.
   - `core/settings.py` `_load_env_files` loads `.env.local` with `override=True`, so it beats real environment variables and breaks two tests in `tests/unit/test_config_mode.py`. Use `override=False`, and add a test.
   - `tests/unit/test_docs_links.py` fails when the git-ignored `docs/learning_docs/` exists. `scripts/docs/check_links.py` skips git-ignored paths.
3. Pins.
   - Poetry 2.3.3 in CI and in `AGENTS.md`. `mcp==2.2.0`.
   - `pgvector/pgvector:0.8.7-pg16`, `prom/prometheus:v3.14.0`, `grafana/grafana:13.2.2`, `ollama/ollama:0.34.4`. Every image by digest.
   - `scripts/check_skips.py` reads an allowlist file instead of hard-coding the MinIO class.
4. Supply chain.
   - Hash-locked exports of the Python dependencies.
   - CycloneDX SBOM for Python and npm, kept as a CI artifact.
   - A licence gate (`pip-licenses --allow-only`, `license-checker-rseidelsohn`) with one allowlist of OSI licences.
   - gitleaks CLI instead of the Action. osv-scanner or grype on the images.
5. CI hygiene and templates.
   - `concurrency` with `cancel-in-progress`, path filters, a `.venv` cache, one composite setup action.
   - Extend `.github/pull_request_template.md`: threat model, licence gate, memory, test delta.
   - Add `planning/sprints/_template/threat-model.md`.
   - Telemetry off in CI: `DEEPEVAL_TELEMETRY_OPT_OUT`, `DO_NOT_TRACK=1`.

## Out of scope
- Replacing Redis Stack, Redpanda or MinIO, compose healthchecks, profiles and localhost binding (012).
- Model defaults and `models.lock` (014).
- Any route, migration or UI change.

## Nav placement
No UI change.

## Questions this sprint closes
- Q1: the WSL notes are written in `docs/getting-started.md`.
- Q36: `queued` is recorded as the agent runtime default in `planning/DECISIONS.md`.
- Q46: marked as carried to Sprint 012, where the Kafka profile changes.
