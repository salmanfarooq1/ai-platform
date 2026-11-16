# Stack: pinned, open source, local

Checked on 2026-11-02 against the Sprint 012 Compose and Poetry lock pins, plus the sources noted below. A pin is a release at least two weeks old, unless a security fix needs a newer one. **UNV** means not verified yet. The Builder of the sprint that adds a component re-checks it and saves the result in `evidence/pins.txt`. Images are pinned by digest from Sprint 011.

## Runtime
| Component | Pin | Licence | Note |
|---|---|---|---|
| Container runtime | Docker Engine (moby) inside WSL, or Podman | Apache-2.0 | **Docker Desktop is not open source** and needs a paid licence in larger companies. Sprint 011 documents Docker Engine and adds a pre-flight check. |
| WSL | `.wslconfig` with `memory=12GB` and `autoMemoryReclaim=gradual` | — | The machine has about 16 GB. Repo stays on ext4, `eol=lf`. |
| Poetry | 2.3.3 | MIT | The lock file was made with 2.3.3. Pin it in CI and `AGENTS.md` (011). |

## Already in the platform (refresh in Sprint 011)
| Component | Today | Pin | Licence | Sprint | Note |
|---|---|---|---|---|---|
| Postgres + pgvector | `pgvector/pgvector:pg16` | `pgvector/pgvector:0.8.7-pg16` | PostgreSQL | 011 | 0.8.7 fixes an IVFFlat buffer overflow. Stay on PG 16. |
| Redis Stack | `redis/redis-stack-server:latest` | replaced by `valkey/valkey-bundle:9.1.3` (Valkey 9.1.2, valkey-search 1.2.1) | BSD-3 | 011 | Redis Stack is not OSI. Search ≥1.2.1 fixes cosine pre-filter normalisation, which our query uses. Code changes: match "already exists", drop unsearched TEXT fields and `SORTBY`, new volume. Fallback: pgvector cache adapter. |
| redis-py | — | `redis==8.1.0` | MIT | 011 | Works with Valkey. |
| Kafka | Redpanda `v24.2.7` | `apache/kafka:4.3.1` | Apache-2.0 | 011 | Redpanda is BSL. KRaft only. Profile renamed `streams` (optional). |
| Object store (dev) | MinIO in the verify script | `chrislusf/seaweedfs:4.47` | Apache-2.0 | 011 | MinIO is archived. Test presigned URLs with boto3. `check_skips.py` moves to an allowlist file. |
| Prometheus | `v3.5.0` | `prom/prometheus:v3.15.1` | Apache-2.0 | 011 | |
| Grafana | `12.0.2` | `grafana/grafana:13.2.4-distroless-slim` | AGPL-3.0 | 011 | Unmodified, optional profile only. |
| MCP SDK | `mcp >=2,<3` | `mcp==2.2.0` | MIT | 011 | Supports protocol 2026-07-28. |
| aiokafka | `0.14.0` | `0.14.0` | Apache-2.0 | — | |
| OpenShell | 0.1.2 | ≥ 0.1.7, re-checked at 027 start (UNV) | Apache-2.0 | 027 | Alpha. Telemetry off. Behind `AGENT_RUNTIME`. 0.1.6 requires gateway auth; 0.1.7 emits OCSF 1.8.0 only. OpenShell-Community was archived on 2026-10-07. |

## Models (Sprint 013)
| Use | Default on CPU | With a GPU (8 GB+) | Size | Licence |
|---|---|---|---|---|
| Runtime | `ollama/ollama:0.40.7` | same | — | MIT |
| Chat and agents | `qwen3:4b-instruct-2507-q4_K_M` (no thinking mode) | `qwen3:8b` | 2.5 / 5.2 GB | Apache-2.0 |
| Routing, small tasks, nightly smoke | `qwen3:1.7b` (CI nightly: `qwen3:0.6b`) | — | 1.4 / 0.5 GB | Apache-2.0 |
| Embeddings | `nomic-embed-text:v1.5` (768 dims, matches `VECTOR(768)`) | same | 0.27 GB | Apache-2.0 |
| Guard model (019) | Select Granite Guardian 3.3 or 4.1 | — | Re-check at sprint start | Apache-2.0 |

The 019 Builder confirms the official Ollama library tag and supply-chain rule before pinning the selected guard model.

- `models.lock` lists each model's digest, licence and source. No SBOM tool covers weights.
- Ollama settings: `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=1`, `num_ctx=8192`, `OLLAMA_KEEP_ALIVE` set.
- CPU speed (estimate): 8–15 tokens per second generation at 4B. A five-step agent loop takes minutes. CI always uses the fake model.
- Ollama may run natively on Windows (MIT) and reach the containers through mirrored networking. Documented, not required.
- `config.py` falls back to `ollama/llama3` (Llama licence, not OSI). Sprint 013 changes it to qwen3.

## New components
| Component | Pin | Released | Licence | Sprint |
|---|---|---|---|---|
| DuckDB | `duckdb==1.5.5` | 2026-07-22 | MIT | 021 |
| DuckLake | spec 1.0, extension bundled in the image | 2026-04-13 | MIT | 021 |
| sqlglot (SQL parse and rewrite) | UNV pin | — | MIT | 021 |
| dbt-core / dbt-duckdb | `1.12.5` / `1.11.0` | 2026-09-15 / 2026-08-07 | Apache-2.0 | 022 |
| OpenLineage | `openlineage-python==1.53.0`, `openlineage-dbt==1.53.0` | 2026-09-01 | Apache-2.0 | 022, 025 |
| datacontract-cli | `1.2.4` (re-check), its `duckdb` extra must match the DuckDB pin | 2026-09/10 | MIT | 023 |
| ODCS / ODPS | v3.2.0 / v1.1.0 | 2026-09 | Apache-2.0 | 023 |
| ydata-profiling | `4.18.4` | 2026-04-22 | MIT | 023 |
| dbt-metricflow | `0.15.0` (needs dbt-core ≥1.11,<1.13). Compile-only, behind our `MetricCompiler` interface. | 2026-09-10 | Apache-2.0 | 025 |
| Open Semantic Interchange (OSI) metric format | spec version pinned at 025 start (UNV) | — | Apache-2.0 | 025 |
| langgraph-checkpoint-postgres | pin at 027 start, same two-week rule (UNV) | — | MIT | 027 |
| Vega-Lite / Vega / vega-embed (charts) | `vega-lite@6.4.1` / `vega@6.2.0` / `vega-embed@7.3.0` (the Vega-Lite and Vega builds that vl-convert 1.9.0 bundles, so browser and PDF charts match) | 2025-09-23 / — / 2026-09-23 | BSD-3 | 029 |
| vl-convert-python (chart to SVG, offline) | `1.9.0.post1` (bundles Vega-Lite 6.4.1, Vega 6.2.0) | 2026-01-21 | BSD-3 | 029 |
| WeasyPrint (HTML to PDF, offline) | `70.0` | 2026-09-08 | BSD-3 | 029 |
| Mailpit (local mail catcher, `mail` profile) | `axllent/mailpit:v1.31.4` | 2026-10-03 | MIT | 029 |
| garak / PyRIT (red team) | `garak==0.17.0` / `pyrit==1.1.0`, in a separate venv or container outside the main lock (they pull torch and hosted-model SDKs) | 2026-09-09 / 2026-09-04 | Apache-2.0 / MIT | 027 |
| LangGraph / langchain-core (already in the platform) | keep the current lock; do not take releases younger than two weeks | — | MIT | 027 |
| agentgateway (spike only) | UNV pin | — | Apache-2.0 | 028 |
| python-pkcs11 / SoftHSM2 (CI only) | `0.10.0` / distro package | — | MIT / BSD-2 | 031 |
| OpenTelemetry Python SDK and instrumentations | UNV pins, one compatible set | — | Apache-2.0 | 028 |
| spaCy model for Presidio | `en_core_web_lg`, version matched to spaCy, pre-fetched | — | MIT | 019 |
| Docling | `docling==2.130.0`, models pre-fetched | 2026-09-22 | MIT | 026 |
| Docling weights | layout model `docling-layout-heron` (Apache-2.0). TableFormer weights are tagged both CDLA-Permissive-2.0 and Apache-2.0; we use them under Apache-2.0 and record it in the 026 ADR, else table structure is off. | — | Apache-2.0 | 026 |
| OPA (optional, `POLICY_ENGINE=opa`) | `openpolicyagent/opa:1.20.2-static` | 2026-09-03 | Apache-2.0 | 030 |
| a2a-sdk | `1.1.5` | 2026-09-21 | Apache-2.0 | 028 |
| Keycloak (test issuer only, CI and nightly) | `quay.io/keycloak/keycloak:26.7.4`. RFC 8693 delegation (`actor_token`, nested `act`) is a preview feature (`--features=token-exchange-delegation`). The 030 spike checks it. Decided 2026-10-11: platform-minted delegation tokens are the default; no preview features in the default stack. | 2026-09-16 | Apache-2.0 | 020 |
| py-spiffe (optional) | `spiffe==0.3.2` (re-check age at sprint start) | 2026-10-01 | Apache-2.0 | 020 |
| Presidio | `presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364`, spaCy model pre-fetched | 2026-07-22 | MIT | 019 |
| COSE | `cwt==3.3.0`, or `cbor2==6.1.5` + `cryptography` (pycose is stale since 2023) | 2026-07 / 2026-10 | MIT | 017 |
| Timestamp authority | `ghcr.io/sigstore/timestamp-server:v2.1.0` (≥2.0.6 for GHSA-xm5m-wgh2-rrg3; date UNV) | UNV | Apache-2.0 | 031 |
| rfc3161-client | `1.0.9` | 2026-09-14 | Apache-2.0 | 031 |
| OTel Collector | `otel/opentelemetry-collector-contrib:0.161.0` | 2026-09-16 | Apache-2.0 | 028 |
| restic | `0.19.1` | — | BSD-2-Clause | 015 |
| rclone | `1.75.2` | — | MIT | 015 |
| OpenTofu | `1.12.9` | — | MPL-2.0 | 031 |

## Added 2026-10-11 (integration first, cloud path, enterprise gaps)
Not checked against registries yet. Each is **UNV** until the sprint that adds it records the pin, release date and licence in `evidence/pins.txt`. The licences below come from the 2026-10-11 research (`review.md`).
| Component | Use | Licence | Sprint |
|---|---|---|---|
| dlt (dlthub) | Batch and API sources (files, SQL databases, SaaS APIs) as a library. Core only; premium sources are commercial and not used. | Apache-2.0 | 022 |
| Trino + OPA access control plugin (optional) | Federated adapter behind `QUERY_ENGINE=trino`, built when a client needs it; DuckDB is the default | Apache-2.0 | on demand |
| sqlglot | SQL parse and rewrite for every adapter | MIT | 021 |
| Postgres logical replication (`pgoutput`) or a dlt incremental source | Change capture, with a replication-slot WAL-growth monitor | PostgreSQL, Apache-2.0 | 022 |
| Apicurio Registry (optional) | Schema registry for client streams | Apache-2.0 | 022 |
| Valentine, bdikit (Magneto) | Schema matching for integration agents | Apache-2.0 (re-check) | 027 |
| OpenMetadata / DataHub import | We call the client's catalog API; we run neither server | — | 023, 025 |
| agentgateway | Optional proxy data plane; our engine is the external authorizer | Apache-2.0 (LF AAIF) | 028 (spike) |
| OpenTofu | Infrastructure as code, one module per cloud. Plain HCL. | MPL-2.0 | 031 |
| OpenBao + External Secrets Operator | Secrets manager and Kubernetes sync | MPL-2.0 / Apache-2.0 | 031 |
| Keycloak 26.8.x (test issuer only) | SCIM 2.0 supported and on by default from 26.8.0 (2026-10-01; inbound only). Replaces the 26.7.4 pin when 020 starts. | Apache-2.0 | 020 |
| pg_textsearch | True BM25 inside Postgres. Check it builds for our Postgres version. | PostgreSQL | 026 |
| RAGAS, TruLens | Retrieval and grounding evals | Apache-2.0 / MIT | 026 |
| Faker | Synthetic rows from a client schema (reference company variants) | MIT | 014 |
| LiteLLM | Locked at `1.103.2`; MIT licence verified. The March 2026 PyPI incident affected versions `1.82.7` and `1.82.8`; neither is in the lock. | MIT | 011 |

## CI and supply chain tools (Sprint 011)
| Tool | Pin | Licence | Use |
|---|---|---|---|
| pip-licenses | `5.5.5` | MIT | Python licence gate with `--allow-only` |
| license-checker-rseidelsohn | `5.0.1` | BSD-3 | npm licence gate |
| cyclonedx-py / cyclonedx-npm | `7.5.0` / `6.0.1` | Apache-2.0 | SBOM |
| syft, grype or osv-scanner | UNV pins | Apache-2.0 | image SBOM and CVE scan |
| gitleaks CLI | UNV pin | MIT | secret scan (the GitHub Action needs a key for organisations) |
| import-linter | UNV pin | BSD-2 | module boundaries (012) |

## Licence gate notes
- Some packages have no licence field on PyPI (for example `openlineage-dbt`, `garak`). The reviewed `licence-exceptions.txt` from 011 names each one, its real licence and the source checked. Nothing else may bypass the gate.
- Pins younger than two weeks at sprint start are replaced by the previous release (decided 2026-10-11). Examples today: `datacontract-cli`, `cbor2`, `valkey-bundle`, and Mailpit `v1.31.4` (released 2026-10-03). Each Builder re-checks ages and records the result in `evidence/pins.txt`. A security fix is the only exception, and it is noted there.
- `ydata-profiling` 4.18.4 needs `numpy<2.4` and `pandas<3`. Watch the resolver when Docling and Presidio share the worker image.

## Rejected, and why
| Option | Reason |
|---|---|
| Docker Desktop | Proprietary. Docker Engine or Podman instead. |
| Redis Stack, Redis 8 under RSAL/SSPL | Not OSI. Valkey bundle instead. |
| OpenMetadata (running it) | Its Python ingestion package is under the Collate Community License, and it needs OpenSearch and 6–8 GB. We import from a client's instance through its API instead. |
| DataHub | 8+ GB. Too heavy for a laptop. |
| Soda Core 4 | Elastic License 2.0. |
| Redpanda | BSL. |
| MinIO | Archived, last image lacks a CVE fix. |
| Marquez | No release since 2025-03. Lineage lives in Postgres. |
| Superset, Metabase, Lightdash, Evidence, Rill | They read the warehouse with their own service account, which bypasses the gateway, grants and receipts. Metabase is also AGPL plus a commercial part. BI is built in as M6 Insights (029). A governed SQL endpoint for external tools gets a spike in 029. |
| Delta Sharing server | Last image 2024. |
| Trino as the default engine | 2–4 GB. DuckDB federates by default. Trino is an optional adapter, built on demand. |
| Debezium | Needs Kafka Connect and about 1.5 GB more. Logical replication or dlt covers change capture (2026-11-08). |
| Keycloak as the shipped IdP | Clients bring their own provider. We ship an OIDC client and SCIM 2.0; Keycloak is the test issuer (2026-11-08). |
| LiteLLM proxy | An extra service. LiteLLM stays a library inside our gateway. |
| A graph memory database | Memory stays in Postgres. |
| Dagster, Airflow | Extra services. The job queue is generalised instead (022). Dagster is the upgrade path. |
| Prompt Guard, Llama models | Llama licence, not OSI. |
| Qwen3Guard | Only third-party GGUF builds in the Ollama library. Weak supply chain. |
| Zitadel | AGPL. Keycloak is Apache-2.0. |
| pycose | Last release 2023. |
| Airbyte | Platform and connectors are under ELv2 (the docs and an older FAQ disagree on connectors). Not OSI. dlt instead. |
| SDV | Business Source License. Faker (MIT) or NeMo Data Designer (Apache-2.0) instead. |
| Terraform CLI as a requirement | BSL 1.1. We write plain HCL and run it with OpenTofu. |
| HashiCorp Vault | BSL 1.1. OpenBao instead. |
| ParadeDB `pg_search` | AGPL. `pg_textsearch` instead. |
| Cube Core, Wren AI as the metric path | They enforce their own row and column rules, which would bypass or duplicate the gateway. MetricFlow compile-only stays. |

## Memory budget (16 GB laptop, estimated, measured each sprint)
| Profile | Services | RAM |
|---|---|---|
| `core` (default) | Postgres, Valkey, API, worker | ~2 GB |
| `models` | Ollama, one chat model loaded (4B, 8k context), embeddings | ~4 GB |
| `lake` | SeaweedFS, plus DuckDB `memory_limit` (default 1 GB) | ~1.5 GB |
| `federation` | Trino (optional, on demand) | ~2–4 GB |
| `streams` | Kafka (optional) | ~1 GB |
| `policy` | OPA (optional) | ~0.1 GB |
| `identity` | Keycloak (test issuer, CI and nightly only) | ~1 GB |
| `guard` | Presidio guard service plus the selected 019 guard model. Measure the model's memory at sprint start. `OLLAMA_MAX_LOADED_MODELS=3` in this profile only. | To measure |
| `mail` | Mailpit (local mail catcher) | ~0.05 GB |
| `trust` | timestamp authority | ~0.1 GB |
| `observability` | OTel collector, Prometheus, Grafana | ~0.8 GB |
| Docling, while parsing | inside the worker | ~2–3 GB |
| PDF reports, while rendering | WeasyPrint and vl-convert inside the worker | ~0.3 GB |

The normal working set (`core`, `models`, `lake`) is about 7.4 GB.

Peak per showcase journey, inside `memory=12GB`. These are the old journey names; 012 redefines the journeys for the new milestones, and each sprint measures them. The cloud track (031) may run on a VM, where this limit does not apply.
| Journey | Profiles | Estimate |
|---|---|---|
| `m0.sh` | core, models | ~6 GB |
| `ma.sh` | core, lake, streams | ~5 GB |
| `mb.sh` | core, lake, models, Docling and PDF in the worker | ~10.8 GB |
| `mc1.sh` | core, models, identity, policy | ~7.1 GB |
| `mc2.sh` | core, lake, models, guard | ~10.8 GB |
| `md.sh` | core, trust | ~2.1 GB |
| `me.sh` | one edition at a time | ≤ the journeys above |
 Running everything at once does not fit in 16 GB with Windows running too. Profiles are switched per task, and each sprint's evidence records a measured `docker stats` line.
