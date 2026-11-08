# Sprint 011: Threat model

## Assets
- The CI pipeline and its tokens (`GITHUB_TOKEN`).
- The dependency tree (Python, npm, images).
- Secrets in the repo history and in local env files.
- Data in Postgres, the cache, the Kafka topics and the object store bucket.
- Service credentials (Postgres, S3 keys, Grafana admin).

## Trust boundaries crossed
- Package registries (PyPI, npm) and image registries into CI and the local machine.
- A local `.env.local` into the process environment.
- The local network (LAN, WSL mirrored networking) to the published container ports.
- The host to the containers.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A dependency or image is swapped upstream under the same tag. | Tampering | Hash-locked exports; external images by digest; upstream profile images are pinned by digest; optional-profile scanner exceptions are scoped by image, CVE, package and expiry. | `export_locks.sh --check`; parsed `check_pins.py`; `test_compose.py::test_optional_security_services_use_digest_pinned_upstream_images`; immutable image identities in the consolidated scan. |
| T2 | A non-OSI or source-available package enters the default stack. | Tampering (licence) | Licence gate with an OSI allowlist; the LiteLLM check. | `test_licence_gate.py` (BUSL fixture fails); `evidence/litellm-check.md`. |
| T3 | A compromised release of a dependency we already use is installed. | Tampering | Pins at least two weeks old; advisory check for LiteLLM; image scan. | `evidence/litellm-check.md`; `evidence/architect-consolidated-images.txt`. |
| T4 | A secret is committed. | Information disclosure | gitleaks CLI over the full history with `--redact`. | `secret-scan` job; `evidence/finish-records-gitleaks.txt`. |
| T5 | A local `.env.local` silently overrides a real environment value (for example a hosted `MODE`). | Tampering | `override=False`. | `test_real_env_beats_env_local`. |
| T6 | A new skip hides a broken service in CI. | Repudiation | Skip allowlist file with a reason per entry and an exact count. | `test_check_skips.py`. |
| T7 | A known critical CVE ships in an image. | Elevation of privilege | Unchanged fixed-critical image scan of final immutable IDs; no advisory ignores. | `evidence/architect-consolidated-images.txt`. |
| T8 | Tools send telemetry from CI. | Information disclosure | `DEEPEVAL_TELEMETRY_OPT_OUT`, `DO_NOT_TRACK=1` at workflow level. | `test_ci_env.py`. |
| T9 | A host on the LAN reaches Postgres, Valkey, Kafka, SeaweedFS or Ollama on a published port. | Information disclosure | Every published port bound to `127.0.0.1`. | `test_compose_profiles_render_with_loopback_ports`; `evidence/stack-compose-final-redacted.txt`. |
| T10 | A service starts with a well-known default password. | Elevation of privilege | Credentials from the environment; explicit local-only defaults; services published only on loopback. Live verification uses generated non-default S3 credentials. | `test_optional_init_jobs_keep_default_outbox_and_environment_credentials`; `evidence/stack-seaweedfs-final-runtime.txt`. |
| T11 | A cache index error is treated as success, so tenant filters are missing. | Information disclosure | Only "already exists" is tolerated, and the existing field check still recreates an index that lacks `tenant_id`. | `test_already_exists_text_of_both_servers`; cache contract tenant-isolation cases on Valkey. |
| T12 | A dependent service starts before its store is ready and runs half-configured. | Denial of service | Healthchecks and `condition: service_healthy`. | `test_images_health_dependencies_and_preserved_old_volumes`. |
| T13 | A presigned URL works longer or wider than meant. | Information disclosure | Live signed GET/PUT plus changed-key and actually expired GET denial checks. | `scripts/verify/seaweedfs_presign.py`; `evidence/stack-seaweed-presign-negative.txt`. |

## Abuse cases
- A pull request edits `licence-exceptions.txt` to let a BUSL package in. The exceptions file needs a reason and a source per line, and review sees it in the diff.
- A pull request adds a skip to the allowlist to hide a failing service. The entry needs a `count` and a written `why`, and the change shows in review.
- A process on the LAN tries `redis-cli -h <host>` and reads cached answers. The localhost binding blocks it.
- Another process or container with access to the Compose network reaches the unauthenticated local model endpoint. Loopback publication limits LAN access; it does not authorize clients on the private network. Cloud inference is disabled and the original model volume is retained during the documented transition.

## OWASP items in scope
- ASI04 (agentic supply chain): dependency, image and licence controls; new images pinned by digest and licence-checked (Valkey BSD-3, Kafka and SeaweedFS Apache-2.0).
- LLM03 2026 (supply chain): the same controls. Model weights are covered in Sprint 013.
- LLM10 2026 (unbounded consumption): Ollama is opt-in by profile.
- Other ASI items: none. No agent behaviour changes.

## Residual risks
- The shared WSL validation host exhibits backward wall-clock steps even when host/container clocks agree. A chain position orders causality; acquiring its lock does not make UTC monotonic. Original runtime settings were restored, and the full backend tier passes unchanged. Chronological audit views may reorder around a clock correction; preserve historical signed timestamps when addressing that existing assumption.
- Most licence inputs remain publisher metadata. The NumPy correction additionally binds the audited wheel and installed members; it does not validate every other publisher claim.
- Path filters can skip tests for an unlisted root; backend and frontend dependency changes both run supply-chain checks, and their condition is covered together with the classifier.
- Kafka in the `streams` profile has no SASL or ACLs until 022. It is bound to localhost meanwhile.
- `127.0.0.1` binding does not stop other local users or processes on the same host.
