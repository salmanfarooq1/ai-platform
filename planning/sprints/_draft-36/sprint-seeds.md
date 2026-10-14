# Sprint seeds: the Architect's scope notes

Each seed is the source for one sprint pack. Pack writers expand a seed into the five files. They do not add scope beyond the seed, and they keep every item in it. "Code facts" are things the Builder must know about the current code.

Baseline at the start of Sprint 011: 1568 backend tests passed, 10 skipped (live MinIO), 207 Vitest, 82 Playwright. Latest migration `0010`.

---

## 011 baseline-hygiene (Kernel, infra)
Scope:
1. Planning drift: update `planning/STATE.md` (sprints 000–010 are on `main`; 010 QA signed off), move `planning/COMMIT_PLAN.md` to `planning/history/`, refresh the stack and scope lists in `AGENTS.md` (Valkey, Apache Kafka, SeaweedFS, local models, scope list from `branching-and-commits.md`), fix `planning/program/README.md` links.
2. Bugs: `core/settings.py` `_load_env_files` loads `.env.local` with `override=True`, so it beats real environment variables and breaks two tests in `tests/unit/test_config_mode.py`. Use `override=False` and add a test. `tests/unit/test_docs_links.py` fails when the git-ignored `docs/learning_docs/` exists locally: make the checker skip git-ignored paths.
3. Pins: Poetry 2.3.3 in CI and `AGENTS.md`; `mcp==2.2.0`; `pgvector/pgvector:0.8.7-pg16`; Prometheus `v3.14.0`; Grafana `13.2.2`; Ollama `0.34.4`; all images by digest. `scripts/check_skips.py` reads an allowlist file instead of hard-coding the MinIO class.
4. Supply chain: hash-locked exports, CycloneDX SBOM (Python and npm) as a CI artifact, licence gate (`pip-licenses --allow-only`, `license-checker-rseidelsohn`) with an allowlist of OSI licences, gitleaks CLI (not the Action), osv-scanner or grype on images.
5. CI hygiene and templates: `concurrency: cancel-in-progress`, path filters, `.venv` cache, one composite setup action. PR template extended (threat model, licence gate, memory, test delta). Add `planning/sprints/_template/threat-model.md`. Telemetry off in CI (`DEEPEVAL_TELEMETRY_OPT_OUT`, `DO_NOT_TRACK=1`).
Acceptance highlights: all suites green with the same counts; the two mode tests pass with a `.env.local` present; licence gate fails on a seeded non-OSI fixture; SBOM artifact produced; gitleaks clean.
Threats: supply chain (ASI04), secrets in CI.
Questions: Q1 (WSL notes), Q36 (record the agent runtime default), Q46 (confirm Kafka settings names, carried to 012).
No migration. No UI change.

## 012 open-source-stack (Kernel, infra)
Scope:
1. Valkey: `valkey/valkey-bundle:9.1.3` replaces `redis/redis-stack-server` in compose and in CI (`tests.yml`, `frontend.yml`). Code facts: `adapters/redis_cache.py` uses `FT.CREATE` (HNSW, cosine), `FT.SEARCH`, `FT.DROPINDEX`; it matches the error text "Index already exists" (Valkey says "Index <name> in database 0 already exists"; match "already exists"); drop the unsearched TEXT fields `response` and `query` and `SORTBY` (KNN is already sorted); test that `RETURN` fetches unindexed fields. New volume name. Keep the cache contract suite green. Write a pgvector cache adapter only as a documented fallback if the spike fails.
2. Kafka: `apache/kafka:4.3.1` (KRaft) replaces Redpanda in the profile, renamed `cdc`. Kafka tests and `scripts/verify/kafka.sh` pass on it. Q42 closed.
3. Object store: SeaweedFS `chrislusf/seaweedfs:4.47` in a `lake` profile with a bucket-init job. `scripts/verify/seaweedfs.sh` replaces `minio.sh`. Presigned URLs tested with boto3. Skip allowlist updated.
4. Runtime: document Docker Engine (moby) inside WSL or Podman as the supported runtime, with a pre-flight script `scripts/preflight.sh` (engine, memory, clock, ports). `.wslconfig` guidance (`memory=`, `autoMemoryReclaim=gradual`).
5. Compose: bind every published port to `127.0.0.1`; healthchecks (`pg_isready`, `valkey-cli ping`, `ollama list`, S3 port); `depends_on: condition: service_healthy`; Ollama moves to a `models` profile; one-shot init jobs (bucket, topics, model pull).
Acceptance highlights: cache contract suite green on Valkey; Kafka suite green on Apache Kafka; S3 contract green on SeaweedFS live; `docker compose config` valid for every profile; no port bound to 0.0.0.0.
Threats: exposed services on the LAN, default passwords.
Questions: Q42, Q45 (topic retention defaults written down), Q20 if touched.
No migration. No UI change.

## 013 module-boundaries (all, infra + small UI)
Scope:
1. Evidence core: move `gateway/record.py`, `gateway/chain.py`, `gateway/receipts.py` (and helpers) into a new `evidence/` package behind a `DecisionSink` port. `enforce()` still fails closed when the sink write fails. No behaviour change.
2. Cross-module ports in `ports/`: `DecisionSink`, `EvidenceLookup`, `DataAccess`, `LineageEmitter`, each with a no-op adapter and a contract suite (real and no-op where both exist).
3. Boundaries: import-linter contracts in CI (modules import only kernel and `ports/`; no module imports another module); `ENABLED_MODULES` validated in `core/settings.py`; a module registry that registers routes, workers and nav; `GET /v1/system/modules`; disabled modules answer `module_disabled` (new reason code); UI nav hides disabled groups.
4. Decision record v2: `record_version` and one canonical serialisation, with an extensible `extensions` map hashed in a fixed order. Old records verify unchanged. Migration (next free after 0010) adds the columns. ADR-0013.
5. Docs and CI: `docs/design/IA.md` (Workspace, Data, Governance, Evidence, Platform; personas: producer, steward, consumer, operator, auditor, agent developer); update `planning/DOMAIN.md` with data-plane terms (dataset, data product, contract, grant, snapshot, listing, steward, purpose); CI edition smoke matrix (Gateway, Assurance, Agents, Data, Full) that boots each edition and runs a smoke set.
Acceptance highlights: full suite green with no behaviour change; import-linter passes and fails on a seeded violation; each edition boots; v1 and v2 records both verify; nav hides a disabled module (Playwright).
Threats: a disabled module leaving a route open; chain verification breaking on old records.
Nav: Platform > Modules (read-only list).

## 014 local-models (Kernel + M2, infra)
Scope:
1. Ollama pinned (`0.34.4`), `models` profile, init job pulls models. Ollama settings (`OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=1`, `num_ctx=8192`, keep-alive).
2. Local defaults: `local` mode chat uses `ollama/qwen3:4b-instruct-2507-q4_K_M`; embeddings stay `ollama/nomic-embed-text` (768). Code facts: the local chat default lives in `core/settings.py` `_LLM_MODEL_DEFAULTS` (a Gemini model today); `config.py` `LLM_CONFIG["fallbacks"]` holds `ollama/qwen2.5` (local) and `ollama/llama3` (others, Llama licence): change both. Hosted providers stay optional adapters.
3. `models.lock`: name, digest, licence, source, size for each model. A check script compares pulled digests with the lock. Licence gate covers models.
4. Model digest in every `model.invoke` decision record (record v2 extension) and in receipts.
5. Profiles: CPU and GPU model profiles documented with measured latency; CI keeps the fake LLM; a nightly job runs `qwen3:0.6b` smoke; `scripts/verify/ollama.sh`. ADR-0014 (local by default, licence gate).
Acceptance highlights: local mode answers with no external network (egress blocked in the test); receipt shows the model digest; lock mismatch fails the check; measured tokens per second recorded.
Threats: model supply chain (ASI04), poisoned weights, digest drift.
Questions: Q32 (embedding prices become 0 for local models).

## 015 reference-company (Kernel, data + docs)
Scope:
1. A fictional distributor, functional names only (no real brands): domains finance (invoices, ledger, budgets), CRM (accounts, contacts with PII, opportunities), HR (salaries, restricted), documents (invoice and contract PDFs generated from the data), and a written data policy in plain language.
2. Deterministic generators in `data/reference-company/` (seeded, small and medium sizes), with a data dictionary.
3. A source Postgres database (`refco_source`, compose profile `lake`) seeded from the generators, plus a change generator script for CDC tests later.
4. Personas and keys: producer (finance engineer), steward, consumer (analyst), operator, auditor, agent developer, created with `scripts/admin/identity.py` and a policy file per persona.
5. Showcase skeleton: `scripts/showcase/m0.sh` (the M0 journey) and a Playwright test for it; `docs/showcase.md` lists the journeys per milestone.
Acceptance highlights: generators are deterministic (hash of output stable); M0 journey passes end to end; no real names or brands (a test scans the generated data against a deny list).
Threats: realistic-looking PII in fixtures (use clearly synthetic patterns).
No migration.

## 016 lakehouse-read-path (M4, slice)
Scope:
1. `QueryEngine` port (`ports/query_engine.py`) and a DuckDB adapter (`duckdb==1.5.5`, DuckLake 1.0 extension installed in the image). New package `dataplane/`. `duckdb` joins the import-lint SDK list.
2. Per-tenant catalogs: database `lakehouse` (created by `scripts/setup_db.sh` and the test fixture), one metadata schema per tenant, one data path prefix per tenant, one SeaweedFS identity per tenant limited to its prefix; a catalog role separate from `gap_app`; catalog and S3 secrets never reach agents.
3. Locked connections: attach only the caller's tenant catalog (read only for reads); then `enable_external_access=false`, allowed paths, no extension autoinstall or autoload, unsigned refused, `memory_limit`, `threads`, timeout, `lock_configuration=true`. Process model: reads on a thread pool with a bounded tenant-keyed connection cache; heavy queries on a query worker.
4. Gateway: new action kind `data.read` (code fact: `gateway/types.py` has no data kinds; also update `KNOWN_TOOLS` and reason codes). Every read pins a snapshot id; the decision record v2 carries it.
5. API: `GET /v1/data/datasets/{id}/preview` and `GET /v1/data/datasets/{id}/snapshots` (read scopes), governed; a `scripts/verify/ducklake.sh`; ADR-0015 with the written exception to strict rule 7.
Acceptance highlights: cross-tenant negative tests all denied (other schema, other path, `read_parquet('s3://other/...')`, `ATTACH`, `COPY TO`, `INSTALL`, `SET`); settings cannot be changed after lock; snapshot id in records; event loop not blocked (heartbeat test like Lab 7.5).
Threats: tenant isolation (critical), exfiltration through DuckDB functions, secrets leakage.
Nav: Data > Datasets (read-only list and preview).

## 017 lakehouse-write-path (M4, slice)
Scope:
1. Dataset registry tables (tenant_id, RLS, GRANT): datasets, tables, schema versions. Additive schema changes are automatic; others are refused until contracts exist (021).
2. Upload to table: CSV and Parquet through a job (size and decompression limits, CSV formula neutralised on export). Single writer per table: advisory lock on the dataset id, retry on DuckLake conflict. The API never writes.
3. Maintenance job on the scheduler: flush inlined data, merge files, expire snapshots, clean up files, under the same lock. Protected snapshots (named in receipts) are kept for the replay window. Lakehouse retention per tenant.
4. Erasure flow: delete rows, force expiry and cleanup, record which receipts can no longer be replayed. Backups runbook: `pg_dump -Fc` of `rag_platform` and `lakehouse` plus the SeaweedFS bucket as one set.
5. Seed load of the reference company into the lakehouse; Data page: datasets, schema, snapshots, governed preview, "query as of" a snapshot.
Acceptance highlights: two concurrent writers on one table never abort the job (lock + retry test); protected snapshot survives expiry; erasure leaves no readable row in any snapshot; seed load reproducible.
Threats: writer races, oversized uploads, erasure incomplete.
Questions: Q27 and Q35 retention, if the scheduler work allows; else 018.
Nav: Data > Datasets.

## 018 pipelines (M4, slice)
Scope:
1. Pipeline definitions (tenant-scoped tables): source, target dataset, schedule (cron), parameters. Run and task history tables.
2. Connectors: Postgres (reads the reference source database with a read-only role), files from the object store, HTTP with an egress allowlist that denies private ranges and compose service names (SSRF test).
3. Scheduler: generalise `workers/scheduler.py` (today only retention purges, interval loop, hard-coded `USER_KINDS`) into cron schedules for any job kind. Skip a run if one is in progress. Backfill with partition parameters.
4. Retention jobs for `jobs`, `outbox`, `processed_events`, raw files, `sandbox_events`, `run_tokens` (Q27, Q35), unless done in 017.
5. Pipelines page: definitions, runs, task logs, run now, backfill. Duration and freshness metrics exported for 044.
Acceptance highlights: the reference finance pipeline loads on schedule; SSRF attempts denied; overlapping run skipped; backfill of three partitions.
Threats: SSRF, credential storage for sources (env or file secrets only).
Nav: Data > Pipelines. ADR-0016.

## 019 transforms-dbt (M4, slice)
Scope:
1. dbt (`dbt-core==1.12.5`, `dbt-duckdb==1.11.0`) runs as a job against the tenant's DuckLake catalog.
2. Per-tenant dbt projects are generated from pipeline definitions and templates. No user-written SQL, macros or Python models in this program step (they would need the sandbox).
3. Packages only from a vendored allowlist (`dbt deps` offline). Profiles generated per run with short-lived secrets, never stored.
4. Incremental models (merge) take the single-writer lock.
5. OpenLineage: a spike proves whether `openlineage-dbt` works with dbt-duckdb on DuckLake; raw events are stored for 025 either way. `DO_NOT_TRACK=1`.
Acceptance highlights: reference finance marts build; a second run is incremental; a package outside the allowlist fails; no secret in any artifact; spike result in evidence.
Threats: code execution through dbt (ASI05), secret leakage in logs and manifests.
Nav: Data > Pipelines (transform steps shown).

## 020 cdc-streaming (M4, infra + small UI)
Scope:
1. Compose profile `cdc`: Apache Kafka with SASL/SCRAM and ACLs, Debezium `quay.io/debezium/connect:3.6.2.Final`. Source Postgres needs `wal_level=logical` (compose command and CI step). Kafka Connect port 8083 not published; secrets through a config provider.
2. Source setup: replication-only role, a publication filtered to listed tables, a heartbeat, a WAL growth alert.
3. Our own sink into DuckLake: micro-batches (10–30 s), dedupe by key keeping the last change, guard by source LSN, Kafka offsets stored in the same DuckLake transaction as the data, `op=d` deletes, initial snapshot from `op=r`, add-column becomes `ALTER TABLE`, other schema changes quarantine the batch. The tenant comes from the connector registration, never from the message.
4. First real Kafka consumer (Q41: name the process that runs it), Q43, Q44 decided. Freshness measured from source commit time (`ts_ms`).
5. A small UI badge: freshness per dataset. `scripts/verify/cdc.sh`; a fake CDC event source for pytest. ADR-0017.
Acceptance highlights: change generator edits appear in the lakehouse; replay after a crash does not double-apply; deletes applied; schema add-column handled; quarantine on narrowing; credentials not visible through any API.
Threats: credential exposure, event spoofing across tenants, replication role scope.
Questions: Q41, Q43, Q44, Q45.
Note: re-embedding of stale vectors is not in this sprint (it moves to 017 or later as a knowledge job).

## 021 data-products-contracts (M4, slice)
Scope:
1. Data products as ODPS 1.1 documents and contracts as ODCS 3.2 documents, stored as validated JSONB (tenant_id, RLS). `datacontract-cli` (re-check pin; its `duckdb` extra must match the DuckDB pin) lints and tests.
2. Contract versions: semver. A native diff marks breaking changes (removed column, narrowed type, tighter rule, changed classification = major). A major version needs a new output port and a deprecation window.
3. Product lifecycle as an explicit table of legal transitions with an audit event per transition: draft, in_review, certified, degraded, deprecated, retired.
4. Classification and sensitivity are required before review. Glossary terms. Aspect types as JSON Schema documents.
5. Catalog search with Postgres full-text search over products, columns and glossary. Products page. ADR-0018.
Acceptance highlights: invalid contract refused with a clear error; breaking change detected; illegal transition refused; search finds a product by a column name.
Threats: contract tampering, unclassified sensitive data.
Nav: Data > Products.

## 022 certification-quality (M4, slice)
Scope:
1. Auto-check registry (named functions): missing owner, missing classification, PII columns not classified, no lineage (stub until 025), stale data, broken SLO.
2. Steward certification: blocking checks must pass; certification is a decision through `enforce()`; requester and steward differ.
3. Contract checks run on DuckDB (dbt tests where the product is dbt-built). Auto-profiling drafts rules from DuckDB `SUMMARIZE` and `ydata-profiling` on a sample; a steward approves drafts.
4. Quality score: weighted pass rates by dimension (completeness, validity, freshness, uniqueness); blocking vs warning; hysteresis so state does not flap; results stored per snapshot id.
5. Scheduled re-evaluation moves products between certified and degraded. Quality page.
Acceptance highlights: a failing blocking check prevents certification; degrade and recover with hysteresis; draft rules need approval; results joined to snapshot ids.
Threats: self-certification, check results tampered.
Nav: Data > Quality.

## 023 access-requests-grants (M4 + M1, slice)
Scope:
1. Listings: a certified product can be listed for other tenants or teams. Listing requires a classification.
2. Access requests with purpose and justification. One approval model (used again by 034): approver group copied onto the request at creation, chains by sensitivity, separation of duties (requester never approves, including stewards on their own products). Approvers are existing principals with the right scope until 035.
3. Grant queue: approved requests become grants through a worker. "Approved" and "granted" are separate states. Grants carry purpose, columns, row filter, expiry.
4. Revocation and expiry. Signed short-lived download URLs for allowed extracts.
5. Marketplace and My access pages; Approvals queue for access requests.
Acceptance highlights: no grant without an approved request; requester cannot approve; expiry removes access; revoked grant blocks the next request.
Threats: approval races (TOCTOU), privilege escalation by self-approval.
Nav: Workspace > Marketplace, Workspace > My access, Governance > Approvals (access requests).

## 024 query-enforcement (M4 + M1, slice)
Scope:
1. Rewrite: parse SQL with sqlglot (duckdb dialect); replace each table with the grant's filtered and masked subquery; only rewritten references allowed. Column masks and row filters come from the grant and the contract classification.
2. Minimum group size for aggregates over classified columns (k-threshold from the contract).
3. Purpose stage (Python) in `enforce()`: the declared purpose must match the grant's purpose; mismatch is a deny. OPA takes this over in 031 without changing behaviour.
4. Cache keys include principal, grant id and grant version. Revocation cancels running queries.
5. Bypass corpus (50+ cases) as tests; a check that file pruning still works after rewriting. ADR-0019.
Acceptance highlights: every bypass case denied; masked column never visible; small groups suppressed; cross-user cache leak test; pruning still prunes.
Threats: SQL injection, mask bypass, inference through aggregates, cache leaks.
Nav: Workspace > Data query (a governed SQL box for analysts with grants).

## 025 lineage (M5, slice)
Scope:
1. New package `lineage/`: a lineage store in Postgres (tenant_id, RLS): jobs, runs, datasets, edges, facets.
2. Ingest OpenLineage events from pipelines (018), dbt (019) and CDC (020) through the event bus (`LineageEmitter` port).
3. Agent facets: `agentRun`, `modelCall`, `decisionRecordId`, each with a published JSON Schema URL (`docs/contracts/lineage/`). Decision ids resolved through `EvidenceLookup`.
4. Redaction: SQL literals never stored, only hashes. Tenant-scoped queries only.
5. Lineage page: product and physical lineage merged, a graph with click-through to decisions. The "no lineage" auto-check in 022 becomes real. ADR-0020.
Acceptance highlights: reference pipeline shows source → raw → mart → product; a facet validates against its schema; no literal in stored events; disabled lineage module leaves other modules working.
Threats: telemetry leaking data, cross-tenant graph reads.
Nav: Data > Lineage.

## 026 semantic-layer-query-guard (M4 + M1, slice)
Scope:
1. Spike first: `dbt-metricflow==0.15.0` with dbt-core 1.12.5 and DuckDB 1.5.5 against a DuckLake attach. If it fails, fall back to curated SQL metrics defined in YAML. Record the result.
2. Semantic models and metrics for the reference finance and CRM marts (gross margin, revenue, pipeline value by region and quarter).
3. Compile only: MetricFlow produces SQL; the SQL then goes through the 024 rewrite and the guard. Filters are typed parameters, never raw strings.
4. Parsed SQL guard: exactly one SELECT; function allowlist (deny `read_*`, `glob`, `getenv`, `query`, `query_table`, `COPY`, `EXPORT`, `INSTALL`, `LOAD`, `SET`, `PRAGMA`, `ATTACH`, `CALL`); every table resolves to a granted relation; EXPLAIN-based row and cost estimate; over the limit is a deny (approval comes in 034).
5. Injection fuzz corpus (50+ cases) in CI; `GET /v1/semantic/metrics` and `POST /v1/semantic/query`. ADR-0021.
Acceptance highlights: spike result recorded; every fuzz case denied; metric answers match a hand-computed result set; over-limit query denied with a clear reason.
Threats: injection (LLM01 2026, ASI05), cost exhaustion.
Nav: Workspace > Ask (metrics panel).

## 027 ask-your-data-agent (M3, slice)
Scope:
1. Agent tools (through `enforce()`): list metrics, describe dataset, query metric, guarded SQL fallback. The LangGraph agent runs inside the sandbox for data runs (Q34); OpenShell is mandatory for data agents (in-process allowed only in tests).
2. Session taint and the lethal-trifecta breaker: any untrusted content taints the run; a tainted run loses tools that can send data out or write. Output stripping of markdown links and images (or a proxy that refuses them).
3. Answer receipts (record v2 extensions): SQL hash, metric ids, snapshot id, result hash, withheld columns and row-filter ids, model digest.
4. Ask-data UI: answer, result table, provenance panel (metric, snapshot, masks), replay button.
5. Evals: a hand-verified set of 40+ questions on the reference company, scored by result-set comparison; abstention cases; leakage tests (masked columns never change answers). Three CI tiers (PR deterministic with the fake model; nightly pinned local model at temperature 0; release red team). Nightly garak and PyRIT runs start here. Eval results stored as signed records.
Acceptance highlights: accuracy above an agreed threshold (record it, Q40); leakage tests pass; tainted run cannot call an outbound tool; replay reproduces the result hash.
Threats: ASI01 goal hijack, ASI02 tool misuse, ASI05, LLM01 prompt injection, data exfiltration.
Questions: Q34, Q40.
Nav: Workspace > Ask.


## 028 governed-dashboards (M6, slice)
1. New module M6 Insights (`insights/`, `ENABLED_MODULES` value `insights`). Tiles read through the `DataAccess` port, the same path as the 027 agent tools. The Data edition adds `insights`.
2. Metric catalog: definition, owner, source products, freshness, quality. A metric is certified only when its source products are certified and a steward approved its definition hash.
3. Explore, then dashboards as versioned JSON documents (`dashboard_spec` v1). Tile kinds: number, line, bar, area, table, text. No raw SQL or chart code.
4. Every tile reads under the viewer's grants, never the author's. One snapshot per dataset per view. A drawer shows the decision id and the receipt.
5. Charts with Vega-Lite (BSD-3), built server side with inline data. Pin an ask-data answer as a tile (metric ids and filters only). ADR-0031.

Acceptance highlights: two personas see different numbers on one dashboard; every tile has its own decision; lineage shows source to dashboard.
Freeze point: tag `v0.28.0` after this sprint.

## 029 reports-alerts (M6, slice)
1. Subscriptions on the 018 scheduler. Each recipient is a principal and gets a copy rendered under their own grants.
2. Offline PDF (vl-convert for SVG, WeasyPrint for PDF, no URL fetches) and CSV (table tiles only, through `data.extract`).
3. In-app inbox by default. SMTP adapter off by default; email carries a link, not data. Local mail catcher in the `mail` profile.
4. Metric alerts on schedule and after ingest, with dedupe and hysteresis. The value follows the recipient's grant.
5. A manifest per run (dashboard version, snapshots, decision ids, file hash), bound to a `report.deliver` decision, plus a lineage event.

Acceptance highlights: two recipients get two different PDFs; a revoked grant withholds tiles on the next run; an alert fires once.

## 030 document-agent (M3 + M4, slice)
Scope:
1. Docling `2.130.0` with model weights and the OCR model pre-fetched into a volume; no network at runtime.
2. Extraction of reference invoices and contracts into tables shaped by an ODCS contract.
3. Review queue: a human approves, edits or rejects each extraction; approved rows publish through the write path (017).
4. Citations: page number and bounding box per extracted field, shown in the UI over the page image.
5. Taint: reading document text taints the run. A malicious-PDF test (hidden instructions to leak data) shows nothing leaves and the tool calls are denied.
Acceptance highlights: extraction accuracy on the reference set recorded; malicious PDF contained; no runtime download (network blocked in the test).
Threats: indirect prompt injection (ASI01, LLM01), poisoned files.
Nav: Data > Documents (review queue).

## 031 policy-engine-opa (M1, slice)
Scope:
1. OPA adapter on the existing seam (code fact: `PolicyEngine` Protocol and `PythonPolicyEngine` in `gateway/policy.py`). OPA `1.20.2-static` as a sidecar in profile `policy`; the Python engine stays the default.
2. One decision-table suite that both engines must pass. `opa test` for the Rego bundle in CI (no server needed).
3. Three outcomes: allow, deny, approval required (until 034, approval required is recorded and treated as deny).
4. Purpose moves into policy without behaviour change. First real tenant policies for the reference company personas as fixtures (Q8).
5. Replay data: the policy bundle hash and the input document hash are stored per decision (record v2 extension), so `opa eval` can reproduce any decision offline. ADR-0022.
Acceptance highlights: both engines agree on every table row; bundle hash in records; offline replay reproduces a stored decision.
Threats: policy bypass when OPA is down (must fail closed), bundle tampering.
Questions: Q8, Q15.
Nav: Governance > Policies.

## 032 policy-authoring (M1, slice)
Scope:
1. ODCS 3.2 agent-context rules ("must never", usage instructions) compiled into policy data per product.
2. AuthZEN Authorization API 1.0 evaluation endpoint (`/access/v1/evaluation`, batch evaluations) mapped onto `enforce()` checks; interop tests.
3. Policy test bench in the UI: write a draft, run it against chosen inputs.
4. What-if: run a draft policy over the last N days of recorded inputs and show the decisions that would change before publishing.
5. Replay of "why was this allowed" for any decision, in the UI and the CLI.
Acceptance highlights: a contract "must never" rule denies a matching agent action; AuthZEN interop tests pass; what-if shows a changed decision; replay matches the stored outcome.
Threats: draft policies leaking into production, replay inputs exposing content (hashes only).
Nav: Governance > Policies (test bench, what-if), Evidence > Decisions (replay).

## 033 mcp-2026-gateway (M1, slice)
Scope:
1. MCP 2026-07-28 with `mcp==2.2.0`: stateless streamable HTTP. Code fact: `api/mcp/transport.py` runs the legacy HTTP+SSE session transport today; keep it only behind a deprecation flag.
2. Policy on `Mcp-Method` and `Mcp-Name` headers; a header that disagrees with the body is rejected (-32020) and writes a deny.
3. Auth: protected resource metadata (RFC 9728), resource indicators (RFC 8707), client ID metadata documents; no token passthrough to downstream servers.
4. Tool definitions pinned by hash; a changed description is denied until approved again. W3C trace context from `_meta` into decision records.
5. A private MCP registry: allow-listed servers with signed manifests. ADR-0023.
Acceptance highlights: a stateless client works; header mismatch denied and recorded; token passthrough impossible (test); changed tool description blocked.
Threats: ASI02 tool misuse, ASI04 supply chain (tool poisoning, rug pull), confused deputy.
Nav: Governance > MCP registry.

## 034 human-approvals (M1 + M2, slice)
Scope:
1. "Approval required" becomes real. An approval is bound to a canonical action hash: SQL or tool arguments, parameters, snapshot id, principal, purpose, policy bundle hash.
2. Single use (nonce), short expiry, re-checked at execution (an approval never overrides a deny), separation of duties. Reuses the approval model from 023.
3. Approval inbox in the console. MCP elicitation for MCP clients (URL mode for anything sensitive). AuthZEN access request and approval profile shape, labelled "draft-compatible".
4. Run stop and override route (`POST /v1/agent/runs/{execution_id}/stop`, Q22). A human oversight log: who oversaw, stops, overrides, approvals.
5. Approver view shows system evidence (query, data touched, policy reason), not the agent's own explanation (ASI09). Over-limit queries from 026 now ask for approval. ADR-0024.
Acceptance highlights: an approval cannot be reused or used for a changed action; the requester cannot approve; stop ends a run and is recorded; the salary journey needs approval.
Threats: ASI09 human-agent trust, approval fatigue, replay of approvals.
Questions: Q22.
Nav: Governance > Approvals.

## 035 identity-sso (Kernel + M1, slice)
Scope:
1. Keycloak `26.7.4` in profile `identity`, realm export in the repo (no secrets). Console sign-in with OIDC (authorization code + PKCE) through the web edge (ADR-0007 session stays the browser model).
2. Roles and groups map to platform scopes through one mapping file, with a test that every group name matches.
3. Service clients for automation (client credentials). API keys and JWTs keep working.
4. A fake OIDC issuer with JWKS for pytest; `scripts/verify/keycloak.sh` runs nightly in CI.
5. Portal anti-pattern tests: TLS verification is never off; a failed state check fails closed; no unsigned or symmetric tokens; no debug bypass; no default passwords.
Acceptance highlights: sign-in works end to end; each anti-pattern test fails when the protection is removed; group mapping test.
Threats: token forgery, CSRF on login, misconfigured roles.
Nav: Platform > Identity.

## 036 delegation-run-identity (M1 + M3, slice)
Scope:
1. Day-one spike: does Keycloak standard token exchange (v2) accept an `actor_token` and emit a nested `act` claim? Record the result.
2. Delegation tokens: Keycloak exchange if the spike passes; else the platform mints them (as run tokens already do), carrying the `act` chain.
3. Rules: `may_act` checked; audience limited per downstream; lifetime at most the run; each hop only narrows scopes (strict rule 5), with tests.
4. SPIFFE-format run ids (`spiffe://<trust-domain>/tenant/<t>/run/<execution_id>`) without SPIRE; SPIRE documented as optional.
5. The delegation chain is stored on every decision (record v2 extension) and shown in the run view. ADR-0025.
Acceptance highlights: spike recorded; a widening exchange is refused; chain visible on decisions; token lifetime bounded.
Threats: ASI03 identity and privilege abuse, confused deputy.
Nav: Governance > Agent runs (delegation chain).

## 037 a2a-agent-registry (M1, slice)
Scope:
1. A2A v1.0 with `a2a-sdk==1.1.5`: inbound A2A calls go through `enforce()`.
2. Signed Agent Cards (JWS) verified; the card digest is stored on decisions.
3. The platform publishes its own signed Agent Card.
4. The registry (from 033) also holds A2A agents with signed manifests; a changed card needs re-approval.
5. agentgateway spike: can it front MCP and A2A traffic with our gateway as the decision point? Result recorded; no dependency added. ADR-0026.
Acceptance highlights: unsigned or tampered card refused; card digest in records; spike recorded.
Threats: ASI07 inter-agent communication, spoofed agents.
Nav: Governance > Agent registry.

## 038 guardrail-models (M1, slice)
Scope:
1. Presidio `2.2.364` stage on input and output (spaCy model pre-fetched), masking by entity type from policy.
2. Local guard model `granite3-guardian:2b` (from `models.lock`) as a stage; its digest and verdict in the decision record.
3. A labelled set for precision and recall with thresholds; a latency budget per stage; dataset hash recorded.
4. The trifecta breaker from 027 becomes policy-driven (OPA data). A fake detector for pytest; `scripts/verify/guard.sh`.
5. Q37 (OpenShell refused file reads) re-checked against the pinned OpenShell. ADR-0027.
Acceptance highlights: precision and recall above thresholds; latency within budget; guard verdict in receipts.
Threats: guardrail evasion, false positives blocking work, model drift.
Questions: Q37.
Nav: Governance > Guardrails.

## 039 governed-memory-autonomy (M3 + M1, slice)
Scope:
1. Agent memory as governed data (tenant_id, RLS): content hash, source, provenance (run, decision id), trust tier, purpose, expiry.
2. Memory writes are actions through `enforce()` with policy; untrusted sources get a low trust tier.
3. Recall filters by trust tier and purpose; memory reads are recorded.
4. Autonomy tiers per agent: tighten automatically (more approvals, fewer tools) on guardrail hits, cost anomalies or eval regressions; each change is a signed policy-change event.
5. Incident log with a serious-incident workflow (EU AI Act Art. 73 shape). ADR-0028.
Acceptance highlights: a poisoned memory write is quarantined; recall excludes low-trust items for sensitive purposes; tier tightening recorded and reversible by a human.
Threats: ASI06 memory poisoning, ASI10 rogue agents.
Nav: Governance > Agent memory, Evidence > Incidents.

## 040 receipts-v2 (M2, infra + small UI)
Scope:
1. COSE_Sign1 receipts with `kid` (library `cwt` or `cbor2` + `cryptography`; not `pycose`), in a SCITT signed-statement shape. Ed25519 receipts keep verifying.
2. Separate keys for receipts, log checkpoints and the timestamp authority; file-mounted secrets; a PKCS#11 adapter slot (SoftHSM in tests).
3. Key rotation and revocation runbook with a tested drill (Q31). Old receipts still verify after rotation.
4. Attestation fields: sandbox image digest, model digest, policy bundle hash (filled where known; a TEE slot left empty).
5. Offline verifier v2 (`scripts/verify/receipt.py`): checks signature, chain and, with the bundle, replays the decision. Q28 decided. ADR-0029.
Acceptance highlights: v1 and v2 receipts verify; rotation drill passes; replay through the verifier matches.
Threats: key compromise, downgrade to v1, forged receipts.
Questions: Q28, Q31.
Nav: Evidence > Receipts.

## 041 transparency-timestamping (M2, infra)
Scope:
1. A local append-only transparency log (Merkle tree, signed checkpoints) for receipts and evidence packs.
2. Local timestamp authority `ghcr.io/sigstore/timestamp-server` (≥2.0.6, re-check the tag date), `rfc3161-client==1.0.9`; chain heads timestamped on a schedule.
3. Optional external anchors (Rekor v2, a public TSA) as adapters, off by default; packs warn when no external anchor is set (Q29).
4. Clock pre-flight (WSL clock drift after sleep).
5. Backup runbook for keys and the log (losing them breaks old receipts). `scripts/verify/tsa.sh`, fake TSA. ADR-0030.
Acceptance highlights: inclusion and consistency proofs verify offline; timestamps verify; external anchor off by default.
Threats: log rewrite, TSA on the same host (documented residual risk).
Questions: Q29.

## 042 evidence-packs (M2, slice)
Scope:
1. Evidence pack export per system and time window: decisions, receipts, proofs, approvals, oversight log, incidents, lineage summary, eval results.
2. The pack is signed and registered in the transparency log.
3. Per-system `high_risk` flag raises the decision retention floor to 183 days; the pack states the retention in force.
4. Audit search and export (CSV, JSON) in the console.
5. Offline pack verification with the verifier v2.
Acceptance highlights: a pack verifies offline; retention floor enforced; search finds a decision by request id.
Threats: packs leaking content (hashes only), tampered exports.
Nav: Evidence > Evidence packs, Evidence > Search.

## 043 compliance-mapping (M2, slice)
Scope:
1. Technical documents in packs: a system card (Annex IV shape), model cards, and an ML-BOM (CycloneDX) for the chat, embedding and guard models with digests.
2. Templates: ISO/IEC 42005 impact assessment and an Art. 27 fundamental rights impact assessment.
3. Mapping tables: EU AI Act Art. 12, 14, 19, 26, 72, 73; ISO 42001 Annex A (Statement of Applicability); NIST AI RMF and AI 600-1; SP 800-53 tags; OWASP ASI01–10 and LLM Top 10 2026. Each mapped row names the test that proves it.
4. The OWASP coverage matrix collects tests written in earlier sprints; a release red-team run (garak, PyRIT, Strix) feeds the pack.
5. A check that the EU AI Act dates in docs match the adopted text on EUR-Lex (Digital Omnibus). Q26 numbers given an owner.
Acceptance highlights: every mapped row links to a passing test or a document; the matrix shows no unowned ASI item.
Questions: Q26.
Nav: Evidence > Compliance.

## 044 observability (Kernel, infra + UI)
Scope:
1. OTel collector `0.161.0` in profile `observability`; API and workers export traces.
2. GenAI semantic conventions behind `OTEL_SEMCONV_STABILITY_OPT_IN`, version pinned; `decision_id` on spans.
3. Grafana dashboards: decisions and denials, cost, pipeline runs, freshness, quality, approvals waiting.
4. Audit analytics with DuckDB over the decision tables, tenant-scoped, hashes only.
5. Redaction rules for spans and logs (no prompt or result text by default).
Acceptance highlights: a trace links an answer to its decision ids; dashboards load from provisioned files; no content in spans (test).
Threats: telemetry leaks (LLM02 2026), cross-tenant analytics.
Nav: Platform > Observability.

## 045 packaging-editions (all, packaging)
Scope:
1. Per-module Python packages with entry points (`platform.modules`) built as wheels.
2. Edition installs: Gateway, Assurance, Agents, Data, Full, each with its compose file or profile set.
3. Release SBOM and licence report for the whole stack, including models from `models.lock`.
4. Upgrade runbook (DuckDB and DuckLake catalog upgrades, Postgres major upgrade, digests) and backup and restore runbook tested on a copy.
5. Edition smoke matrix becomes a release gate.
Acceptance highlights: each edition installs from wheels on a clean machine and passes its smoke set; restore from backup works.

## 046 showcase-walkthrough (all, docs + e2e)
Scope:
1. One scripted walkthrough per milestone (`scripts/showcase/m0.sh` to `me.sh`) on the reference company.
2. Playwright coverage for every journey.
3. Landing page and How it works page updated with the full chain story.
4. Final docs pass: README, getting started for a fresh laptop, architecture, ADR index.
5. `planning/STATE.md` and `ROADMAP.md` closed for program 2; follow-ups listed for program 3 (a governed SQL endpoint for external BI tools, Trino, Dagster, hosting).
Acceptance highlights: a fresh clone runs the full walkthrough with documented commands; every journey passes.
