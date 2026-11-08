# Sprint 011 stack implementation report

Status: stack-owned implementation and final SeaweedFS image checks are complete. Whole-sprint acceptance remains open for the consolidated final tiers, common image-gate rerun and acceptance review.

## Changes
- Valkey Search replaces the default cache service and CI cache service. The existing CachePort and Redis wire protocol stay. Index creation handles both server messages, unsearched response/query fields are returned without indexing them, and KNN uses its existing order. Index-metadata outages still become CacheUnavailable.
- Compose defaults are Postgres, Valkey and worker. Streams, lake, models and observability remain optional. Published ports are loopback-only; dependencies wait for healthy services, and bucket/topic/model initialization is explicit. Postgres image/volume handling is documented separately.
- Apache Kafka 4.3.1 and SeaweedFS 4.47 use build-only security recipes with pinned inputs. Kafka retains the upstream broker and replaces fixed OpenSSL packages. SeaweedFS rebuilds its Go executable with the reviewed networking closure. Both service and init containers build from the same reviewed Dockerfile; neither has an upstream image override. Operator docs require explicit builds before starting these profiles.
- Ollama uses the reviewed build-only 0.40.7 recipe, disables cloud inference and startup blob pruning, and mounts `ollama_data_v0407`; the original `ollama_data` remains available. The upgrade and backup procedure is in `docs/ollama-upgrade.md`.
- Preflight checks the engine, memory, clock and port ownership. Product docs cover the local profiles and upgrade boundaries. Keyword-search docs describe Postgres full-text `ts_rank`; public compatibility names stay.

## Captured checks
| Check | Evidence | Result |
|---|---|---|
| Cache contracts with redis-py 8.1.0 and Valkey 9.1.3 | `evidence/stack-cache-valkey-final.txt`, `evidence/stack-cache-error-recheck.txt` | 34 contract cases and 6 focused cache error cases passed |
| Fixed-critical Valkey scan | `evidence/stack-valkey-scan.txt` | Passed |
| Kafka child build and fixed-critical scan | `evidence/stack-kafka-security-build-recheck.txt`, `evidence/stack-kafka-security-scan.txt` | Passed |
| Live Kafka contracts and flow | `evidence/stack-kafka-final-live.txt` | 21 passed |
| SeaweedFS final artifact identity, scan and SBOM | `evidence/stack-seaweedfs-final-scan.txt`, `evidence/stack-seaweedfs-final-sbom.cdx.json` | Immutable image `sha256:2c05e29b20d6f1e68fceaa0817c7c26f220262a13bc2971f23d87e4e840d8072`; unchanged fixed-critical gate passed. SBOM has 384 components and 3 fixed findings below the threshold (2 high, 1 medium); ignore list is empty. |
| SeaweedFS final live contracts and signed URL checks | `evidence/stack-seaweedfs-final-runtime.txt`, `evidence/stack-seaweed-presign-negative.txt` | 10 object-store cases passed; SigV4 PUT/GET passed, and changed-key plus expired GET requests both returned 403 using generated non-default credentials. No credential or signed URL was logged. |
| Build-only security recipe regression and lint | `evidence/stack-compose-security-build-test.txt`, `evidence/stack-compose-security-lint.txt` | 8 compose tests passed; Kafka, Ollama and both SeaweedFS services require their reviewed Dockerfiles and have no image key. Ruff passed. |
| Final Compose profile rendering | `evidence/stack-compose-final-redacted.txt` | Default services are Postgres, Valkey and worker; all profiles render, all published ports are loopback-only, and the Ollama recipe, flags and `ollama_data_v0407` mount are present. Environment values were omitted. |
| Default Compose live boot | `evidence/stack-default-final-live.txt` | Fresh project-scoped volumes; owner migrations completed inside the captured app image; Postgres, Valkey and worker reached healthy on isolated loopback ports. The exact default set ran without Kafka. Services were stopped afterward and volumes retained. |
| Preflight success and failure path | `evidence/stack-preflight-final-recheck.txt`, `evidence/stack-preflight-bad-engine-final.txt` | Passed with isolated port overrides; the invalid-engine stub failed as expected. No service was started for preflight. |
| Keyword-search naming | `evidence/stack-keyword-naming-final.txt` | Code and product docs continue to identify `ts_rank` and the public compatibility names. |
| Docs links | `evidence/stack-final-doc-links.txt` | 35 files checked, no problems |
| Final runtime memory | `evidence/stack-memory-final.txt` | Valkey 14.18 MiB, Kafka 473.9 MiB, SeaweedFS 128.9 MiB. Measured after live verification, not as an idle benchmark. |
| Pins and sources/build service discovery | `evidence/stack-pins.txt`, `evidence/stack-pins-validation.txt`, `evidence/stack-built-services-final.txt` | Exact registry, source and package hashes recorded; the image gate discovers Kafka, Ollama and SeaweedFS services and init jobs. |
| Legacy Compose retirement and inventory guard | `evidence/compose-legacy-retirement.txt`, `evidence/compose-final-inventory.txt`, `evidence/compose-indirection-tests.txt`, `evidence/compose-indirection-lint.txt`, `evidence/compose-indirection-standard-check.txt`, `evidence/compose-indirection-compose-images-check.txt`, `evidence/compose-indirection-built-services-check.txt` | Legacy launcher moved byte-identically to `planning/history/`; only `docker-compose.yml` remains at root. A shared validated reader rejects unregistered root Compose files, top-level `include` and service-level `extends` in standard, `--compose-images` and `--built-services` modes. The 56-test control module includes 9 extra-filename and 6 include/extends CLI regressions; Ruff and all three current-inventory modes pass. |
| Supply-chain control module and docs checks | `evidence/compose-indirection-tests.txt`, `evidence/compose-indirection-lint.txt`, `evidence/compose-retirement-doc-links.txt` | 56 control tests passed; Ruff passed; 35 docs files checked without link issues. |

## Remaining acceptance work
- Root owns the consolidated final test tiers and common image-gate rerun across all final artifacts.
- Whole-sprint acceptance remains open until all remaining Sprint 011 checks and evidence are reconciled.

No migration, API change, commit, push, merge, registry publication or paid resource was used. The primary Builder consolidates whole-sprint acceptance and proposed human commit blocks.
