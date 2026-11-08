# Sprint 011: Baseline and stack. Requirements

Platform (Kernel). Infrastructure and bounded dependency cleanup: planning files, settings, CI, supply chain, compose, CI services, the cache adapter and verify scripts. No route or schema change. The selected MCP compatibility and UI licence amendments are defined below. Part a covers items 1–6 and part b items 7–11; all checks must pass on the final stack before acceptance. Replacement work may proceed while the superseded dependency gates are red, as specified in `architect-disposition.md`.

Source: old 011, old 012, plus new scope (five-direction review: LiteLLM check, keyword-search naming, Kafka optional).

## Scope

### Part a: baseline hygiene
1. **Planning drift.**
   - `planning/STATE.md`: sprints 000 to 010 are on `main` (PR #1 merged), and Sprint 010 is QA signed off. Remove the leftover "Awaiting QA" wording.
   - Move `planning/COMMIT_PLAN.md` to `planning/history/`.
   - `AGENTS.md`: refresh the stack list (Valkey, Apache Kafka as an optional profile, SeaweedFS, local or hosted models), and add the commit scope list from `planning/program/branching-and-commits.md`.
   - Fix the links in `planning/program/README.md`.
2. **Bugs.**
   - `core/settings.py` `_load_env_files` loads `.env.local` with `override=True`, so it beats real environment variables and breaks two tests in `tests/unit/test_config_mode.py`. Use `override=False`, and add a test.
   - `tests/unit/test_docs_links.py` fails when the git-ignored `docs/learning_docs/` exists. `scripts/docs/check_links.py` skips git-ignored paths.
3. **Pins.**
   - Poetry 2.3.3 in CI and in `AGENTS.md`. `mcp==2.2.0`.
   - Baseline versions: `pgvector/pgvector:0.8.7-pg16`, `prom/prometheus:v3.14.0`, `grafana/grafana:13.2.2`, `ollama/ollama:0.34.4`. Verified compatible security replacements follow `architect-disposition.md`. Every external base/runtime image is pinned by digest. A build-only security image requires hash-pinned inputs, captured output identity/SBOM and the same final scan/contracts in CI.
   - A pin younger than two weeks at sprint start is replaced by the previous release (decided 2026-10-11).
   - `scripts/check_skips.py` reads an allowlist file instead of hard-coding the MinIO class.
4. **Supply chain.**
   - Hash-locked exports of the Python dependencies.
   - CycloneDX SBOM for Python and npm, kept as a CI artifact.
   - A licence gate (`pip-licenses --allow-only`, `license-checker-rseidelsohn`) with one allowlist of OSI licences.
   - gitleaks CLI instead of the Action. osv-scanner or grype on the images.
5. **LiteLLM check** (new).
   - Verify the licence of the exact locked `litellm` version from its wheel metadata and the repo `LICENSE` at that tag. One review reported a licence change.
   - Check the reported March 2026 PyPI incident against the project's own advisories: affected versions, and whether our lock or any past lock used one.
   - Record both in `evidence/litellm-check.md`. If the licence is not OSI or our version is affected, raise a blocker in `planning/QUESTIONS.md` and stop that item.
6. **CI hygiene and templates.**
   - `concurrency` with `cancel-in-progress`, path filters, a `.venv` cache, one composite setup action.
   - Extend `.github/pull_request_template.md`: threat model, licence gate, memory, test delta.
   - Keep the reusable template at `planning/sprints/011-baseline-and-stack/threat-model-template.md`; promotion to the shared template folder is outside this sprint's folder boundary.
   - Telemetry off in CI: `DEEPEVAL_TELEMETRY_OPT_OUT`, `DO_NOT_TRACK=1`.

### Part b: open-source stack
7. **Valkey replaces Redis Stack.**
   - `valkey/valkey-bundle:9.1.3` (Valkey 9.1.2, valkey-search 1.2.1) in compose and in CI (`tests.yml`, `frontend.yml`), or the previous release if 9.1.3 is younger than two weeks.
   - `adapters/redis_cache.py`:
     - Match "already exists" (Valkey says "Index <name> in database 0 already exists").
     - Drop the unsearched TEXT fields `response` and `query`, and `SORTBY` (KNN is already sorted).
     - A test proves `RETURN` still fetches the unindexed fields.
     - New volume name.
   - The cache contract suite stays green. A pgvector cache adapter is written only as a documented fallback if the spike fails.
8. **Apache Kafka replaces Redpanda**, as an optional profile.
   - `apache/kafka:4.3.1` (KRaft) in the profile, renamed `streams`.
   - The outbox stays the default event bus. Nothing in the default set needs Kafka.
   - The Kafka tests and `scripts/verify/kafka.sh` pass on it.
9. **Object store.**
   - SeaweedFS `chrislusf/seaweedfs:4.47` in a `lake` profile, with a bucket-init job.
   - `scripts/verify/seaweedfs.sh` replaces `scripts/verify/minio.sh`. Presigned URLs are tested with boto3.
   - The skip allowlist is updated.
10. **Runtime and compose.**
    - Document Docker Engine (moby) inside WSL, or Podman, as the supported runtime. Add `scripts/preflight.sh` (engine, memory, clock, ports) and `.wslconfig` guidance.
    - Bind every published port to `127.0.0.1`.
    - Healthchecks with `depends_on: condition: service_healthy`.
    - Ollama moves to a `models` profile.
    - One-shot init jobs: bucket, topics, model pull.
11. **Keyword-search naming** (new).
    - The "BM25" leg is Postgres full-text `ts_rank` (`adapters/pg_knowledge.py`), not true BM25. `docs/architecture.md`, ADR-0005, `README.md` and `STATE.md` say so.
    - A code comment marks it at `search_bm25` and `bm25_score`.
    - The public API values (`bm25_only`, `bm25_score`) stay for compatibility. True BM25 comes in 026.

## Out of scope
- Model defaults, `models.lock` and hosted providers (013).
- Kafka SASL, ACLs, Debezium and any Kafka consumer (022). Per-tenant SeaweedFS identities (021).
- Any route or migration change, except the documented cache fallback migration; UI changes outside the bounded licence migration.
- Changed from old 011 and 012: the two sprints are one. The Kafka profile is named `streams` and is optional. The LiteLLM check and the naming fix are new.

## Nav placement
No navigation change. The licence migration preserves existing landing behavior and fonts.

## Questions this sprint closes
- Q1: the WSL notes are written in `docs/getting-started.md`.
- Q36: `queued` is recorded as the agent runtime default in `planning/DECISIONS.md`.
- Q42: Redpanda (BSL) is replaced by Apache Kafka.
- Q45: topic retention defaults are written in `docs/operations.md` and set by the topic job.
- Q46: the Kafka setting names are confirmed against the new profile.
- Q20: only if the stale-vector count is touched while moving to Valkey. Otherwise it stays open.

## Selected MCP compatibility amendment
The Architect review authorizes the expected-error compatibility work for MCP 2.2.0 inside `api/mcp/`. Translate known `GatewayDenied` results to the SDK expected tool/resource error types using controlled reason codes. Preserve route shapes, schemas, denial reasons, gateway enforcement and input-guardrail JSON. Unexpected exceptions must retain SDK masking and must not expose exception text in responses or application logs. Add a sentinel-secret regression and retain the existing policy-denial and concurrent-reply assertions. No transport redesign.

## Selected dependency and sequencing amendments
`architect-disposition.md` selects the proposed byte-preserving font/landing dependency migration, exact-artifact NumPy audit, compatible fixed image assessment and replacement-first work order. It also retires the obsolete, unreferenced production Compose launcher verbatim into history and rejects unregistered active root Compose files. Hosting remains parked until the new 015 bundle. The OSI-only policy, original assertions, critical-scan threshold and final acceptance checks are unchanged. `licence-remediation.md` defines the UI source boundary. Full UI checks and all browser cases run after this migration.
