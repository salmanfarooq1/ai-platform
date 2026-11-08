# Sprint 011: Blueprint

## Part a: baseline hygiene
- **Contract:** no route change. The OpenAPI snapshot test proves `docs/api/openapi.json` is unchanged.
- **Ports and adapters:** none in part a.
- **Settings:** `_load_env_files` calls `load_dotenv(..., override=False)` for `.env.local` and for `.env`. Order of precedence: real environment, then `.env.local`, then `.env`. Which file is read stays the same (`.env.local` if present, else `.env`).
- **Data:** no migration.
- **Gateway and events:** no change.
- **UI:** select only the licence-remediation boundary: retain exact font assets/notices, replace the font wrapper and GSAP landing consumers with native browser behavior, and preserve the visual and reduced-motion contracts. No route, copy, layout, token or console feature change. Full UI checks run after the migration.
- **Pins:**
  - `pyproject.toml`: `mcp==2.2.0`, then `poetry lock` with Poetry 2.3.3.
  - `docker-compose.yml`, both workflows and the `Dockerfile` base image: pinned tag plus `@sha256:` digest. Pins, digests and release dates are saved in `evidence/pins.txt`.
  - Any pin younger than two weeks at sprint start is replaced by the previous release, and the reason is noted.
- **Skip allowlist:**
  - `tests/skip_allowlist.json` is a list of `{classname, name_contains, reason_prefix, count, why}`.
  - `poetry run python scripts/check_skips.py REPORT.xml [--allowlist PATH]` reads it. The default path is that file.
  - The expected skip count is the sum of the `count` fields, so no sprint passes a number on the command line.
  - It starts with one entry: the live-MinIO skip, count 10. Part b replaces it with the SeaweedFS entry.
- **Supply chain (`scripts/supply_chain/`):**
  - `export_locks.sh`: `poetry export --with-hashes` (plugin `poetry-plugin-export`, pinned) writes `requirements/main.txt` and `requirements/dev.txt`. CI fails when they drift from `poetry.lock`.
  - `sbom.sh`: `cyclonedx-py` 7.5.0 (Python environment) and `@cyclonedx/cyclonedx-npm` 6.0.1 (`ui/`) write `sbom/python.cdx.json` and `sbom/npm.cdx.json`. CI uploads both as one artifact.
  - `licence_gate.sh`:
    - `pip-licenses` 5.5.5 `--allow-only` on the main group, and `license-checker-rseidelsohn` 5.0.1 `--production --onlyAllow` in `ui/`.
    - One allowlist: `osi-licences.txt` (SPDX ids, OSI-approved only).
    - Packages with missing or odd metadata go in `licence-exceptions.txt`, each with the licence found by hand, the source checked and a reason.
    - A `--fixture DIR` flag runs the same check on a test fixture.
  - Image scan: osv-scanner or grype (pin chosen and saved in `evidence/pins.txt`) on the built app image and the pinned compose images. It fails on a critical finding that has a fix. An ignore file holds each accepted finding with a reason.
- **LiteLLM check:** `scripts/supply_chain/check_package.py litellm` prints the locked version, the wheel's licence metadata, the `LICENSE` file inside the wheel and its hash. The Builder adds the advisory lookup by hand in `evidence/litellm-check.md`, with links to the project's own advisory or release notes. No code depends on the result unless it is a blocker.
- **CI (`.github/`):**
  - `actions/setup/action.yml`, a composite action:
    - Python 3.11, `pipx install poetry==2.3.3` and `virtualenvs.in-project true`.
    - Cache of `.venv` keyed on the OS, Python version and `poetry.lock` hash.
    - `poetry install` with an input for the groups.
  - Every job of `tests.yml` and `frontend.yml` uses it. Each workflow has `concurrency: {group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true}`.
  - Path filters:
    - Docs-only and planning-only changes skip the test jobs, through a filter job whose result the required jobs read.
    - `ui/**` changes run the frontend workflow.
    - Backend paths and `docs/api/openapi.json` run both.
  - The `secret-scan` job runs the gitleaks CLI (pinned version, checksum checked) with `--redact` over the full history. `.gitleaksignore` keeps its two reviewed entries.
  - New `supply-chain` job: lock drift, SBOM artifact, licence gate and image scan.
  - Workflow-level env: `DEEPEVAL_TELEMETRY_OPT_OUT=YES`, `DO_NOT_TRACK=1`.
- **Templates:**
  - `.github/pull_request_template.md` adds: acceptance table, threat model signed off, licence gate, memory measured for new services, test delta against the baseline, migrations listed.
  - `planning/sprints/011-baseline-and-stack/threat-model-template.md` copies the shape in `planning/program/sprint-template.md`. The corrective handoff reconciles its location with the prohibition on changing other sprint folders; shared-template promotion is outside this scope.

## Part b: open-source stack
- **Ports and adapters:**
  - `adapters/redis_cache.py` keeps the `CachePort` and the class name. Pin `redis==8.1.0` (works with Valkey).
  - `_ft_create`: the schema is `embedding` VECTOR HNSW, then the TAG and NUMERIC fields. No TEXT fields.
  - `ensure_semantic_index`: tolerate an error whose text holds "already exists" (both servers). Any other error still raises `CacheUnavailable`.
  - `semantic_lookup`: no `SORTBY`. `RETURN 3 response score query` stays.
  - Fallback, only if the Valkey spike fails:
    - `adapters/pg_semantic_cache.py` behind the same port, selected by a `SEMANTIC_CACHE=valkey|postgres` setting validated in `core/settings.py`.
    - A migration for its table.
    - Record the spike result in `evidence/valkey-spike.txt` either way.
  - `REDIS_URL` description: "Valkey or Redis URL. The server needs a search module (valkey-search)."
- **Data:** no migration, unless the fallback is taken.
- **Compose (`docker-compose.yml`):**
  - Default services (`postgres`, `valkey`, `worker`):
    - Ports `127.0.0.1:5432:5432` and `127.0.0.1:6379:6379`.
    - The service is renamed `valkey` and the volume is `valkey_data`.
    - The worker's `REDIS_URL` points at `valkey`.
  - Healthchecks: `pg_isready -U postgres`, `valkey-cli ping`, `ollama list`, and a TCP check on the S3 port for SeaweedFS. `depends_on` uses `condition: service_healthy`.
  - Profile `models`: `ollama` (pin from part a) on `127.0.0.1:11434`, and `ollama-pull`, a one-shot job that pulls `nomic-embed-text:v1.5`.
  - Profile `streams`:
    - `kafka` (`apache/kafka:4.3.1`, KRaft, one node) on `127.0.0.1:19092` for the host and `kafka:9092` inside.
    - `kafka-topics`, a one-shot job. Topics: `platform.gateway.decision`, `platform.ingest.completed` and `platform.gateway.purge`, each with `.dlq`, 3 partitions.
    - CloudEvent types keep the `.v1` suffix.
    - `retention.ms` is written in the job and in `docs/operations.md` (Q45).
  - Profile `lake`: `seaweedfs` (`chrislusf/seaweedfs:4.47`, `server -s3`, `127.0.0.1:8333`) and `seaweedfs-init`, a one-shot job that creates the bucket named by `S3_BUCKET`. Access keys come from the environment.
  - Profile `observability` keeps its two services.
  - Every image stays pinned by digest. No default password in compose: values come from the environment with a local-only default, as `APP_DB_PASSWORD` does.
- **CI:** the `redis` service in `tests.yml` and `frontend.yml` becomes `valkey/valkey-bundle` by digest, with health command `valkey-cli ping`.
- **Scripts:**
  - `scripts/verify/kafka.sh` uses `--profile streams` and the `kafka` and `kafka-topics` services.
  - `scripts/verify/seaweedfs.sh` replaces `scripts/verify/minio.sh`. It starts the `lake` profile, runs the object store contract suite live, and does a presigned GET and PUT with boto3.
  - `tests/contracts/test_object_store_contract.py`: the live parameter is `seaweedfs`, with settings `S3_LIVE_ENDPOINT`, `S3_LIVE_ACCESS_KEY`, `S3_LIVE_SECRET_KEY` and `S3_LIVE_BUCKET`. `tests/skip_allowlist.json` names the new class, name and reason.
  - `scripts/preflight.sh` checks:
    - the engine (`docker info` or `podman info`), with a warning when it is Docker Desktop
    - free memory against the profile budget in `planning/program/stack.md`
    - clock skew (container clock against the host)
    - that ports 5432, 6379, 8000 and 5173 are free or held by our containers
    
    It exits 1 on a failed check.
- **Keyword-search naming:**
  - A comment at `search_bm25` (`adapters/pg_knowledge.py`) and at the fusion weights (`api/services/retriever.py`) says the leg is Postgres `ts_rank` full-text ranking.
  - `docs/architecture.md`, `docs/adr/0005-ports-and-adapters.md` (a dated note), `README.md` and `STATE.md` say "keyword search (Postgres full-text)".
  - The API values `bm25_only` and `bm25_score` do not change.

## Tests
- `tests/unit/test_config_mode.py`: `test_real_env_beats_env_local` (a `.env.local` in a temp dir sets `MODE=prod`, the environment sets `MODE=local`, the environment wins). The two existing mode tests pass with a `.env.local` present.
- `tests/unit/test_docs_links.py`: `test_git_ignored_paths_are_skipped` (a temp git repo with an ignored folder holding a broken link).
- `tests/unit/test_check_skips.py`: an allowed skip passes, an unknown skip fails, a wrong count fails, a missing allowlist file fails.
- `tests/unit/test_licence_gate.py`: a fixture with a `BUSL-1.1` package fails the gate; an all-MIT fixture passes.
- `tests/unit/test_ci_env.py`: both workflows set the two telemetry keys.
- Cache contract suite on Valkey (CI and local). `test_index_create_is_idempotent_on_valkey`, `test_return_fetches_unindexed_fields`, `test_already_exists_text_of_both_servers`.
- Kafka suite on Apache Kafka through `scripts/verify/kafka.sh`.
- `tests/unit/test_compose.py`: `docker compose config` parsed for every profile. No published port without `127.0.0.1`. Every service is in a profile or has a healthcheck. Every image has `@sha256:`. No literal secret except named local defaults.
- `tests/unit/test_preflight.py`: the script's checks with stubbed commands.

## Docs
- `AGENTS.md` (Poetry 2.3.3, stack, scope list, licence gate command), `CONTRIBUTING.md` (licence gate, SBOM, how to add an exception).
- `docs/getting-started.md` (WSL notes, Q1, Docker Engine or Podman, `.wslconfig`, preflight), `docs/deployment.md` (profiles), `docs/operations.md` (Valkey, Kafka as optional, SeaweedFS, topic retention), `docs/configuration.md` (regenerated), `docs/architecture.md` (keyword search).
- `planning/DECISIONS.md` (Q36), `planning/STATE.md`, `CHANGELOG.md`.

## Selected MCP compatibility amendment
The Architect review authorizes the expected-error compatibility work for MCP 2.2.0 inside `api/mcp/`. Translate known `GatewayDenied` results to the SDK expected tool/resource error types using controlled reason codes. Preserve route shapes, schemas, denial reasons, gateway enforcement and input-guardrail JSON. Unexpected exceptions must retain SDK masking and must not expose exception text in responses or application logs. Add a sentinel-secret regression and retain the existing policy-denial and concurrent-reply assertions. No transport redesign.

## Autonomous continuation amendment
`architect-disposition.md` governs the bounded UI migration, artifact audit and compatible security-image work. Replacements may be implemented before the temporary part-a dependency failures are resolved. Keep those failures recorded and all acceptance boxes truthful. All final gates still pass before Sprint 011 acceptance or Sprint 012 implementation. An artifact correction must bind the exact audited distribution and preserve provenance/notices; it cannot waive a non-OSI component that actually ships.
