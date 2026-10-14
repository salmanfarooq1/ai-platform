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
| T1 | A dependency or image is swapped upstream under the same tag. | Tampering | Hash-locked exports, images by digest. | `export_locks.sh` drift check in CI; `test_compose.py::test_images_by_digest`; pins grep in `evidence/pins.txt`. |
| T2 | A non-OSI or source-available package enters the default stack. | Tampering (licence) | Licence gate with an OSI allowlist; the LiteLLM check. | `test_licence_gate.py` (BUSL fixture fails); `evidence/litellm-check.md`. |
| T3 | A compromised release of a dependency we already use is installed. | Tampering | Pins at least two weeks old; advisory check for LiteLLM; image scan. | `evidence/litellm-check.md`; `evidence/image-scan.txt`. |
| T4 | A secret is committed. | Information disclosure | gitleaks CLI over the full history with `--redact`. | `secret-scan` job; `evidence/gitleaks.txt`. |
| T5 | A local `.env.local` silently overrides a real environment value (for example a hosted `MODE`). | Tampering | `override=False`. | `test_real_env_beats_env_local`. |
| T6 | A new skip hides a broken service in CI. | Repudiation | Skip allowlist file with a reason per entry and an exact count. | `test_check_skips.py`. |
| T7 | A known critical CVE ships in an image. | Elevation of privilege | Image scan in CI with a reasoned ignore file. | `evidence/image-scan.txt`. |
| T8 | Tools send telemetry from CI. | Information disclosure | `DEEPEVAL_TELEMETRY_OPT_OUT`, `DO_NOT_TRACK=1` at workflow level. | `test_ci_env.py`. |
| T9 | A host on the LAN reaches Postgres, Valkey, Kafka, SeaweedFS or Ollama on a published port. | Information disclosure | Every published port bound to `127.0.0.1`. | `test_compose.py::test_no_port_on_all_interfaces`; `evidence/ports.txt`. |
| T10 | A service starts with a well-known default password. | Elevation of privilege | Credentials from the environment; local-only defaults documented; no default for S3 keys. | `test_compose.py::test_no_literal_secret_in_compose`. |
| T11 | A cache index error is treated as success, so tenant filters are missing. | Information disclosure | Only "already exists" is tolerated, and the existing field check still recreates an index that lacks `tenant_id`. | `test_already_exists_text_of_both_servers`; cache contract tenant-isolation cases on Valkey. |
| T12 | A dependent service starts before its store is ready and runs half-configured. | Denial of service | Healthchecks and `condition: service_healthy`. | `test_compose.py::test_dependencies_wait_for_health`. |
| T13 | A presigned URL works longer or wider than meant. | Information disclosure | The contract checks expiry and that the URL names one key. | `scripts/verify/seaweedfs.sh` presigned cases. |

## Abuse cases
- A pull request edits `licence-exceptions.txt` to let a BUSL package in. The exceptions file needs a reason and a source per line, and review sees it in the diff.
- A pull request adds a skip to the allowlist to hide a failing service. The entry needs a `count` and a written `why`, and the change shows in review.
- A process on the LAN tries `redis-cli -h <host>` and reads cached answers. The localhost binding blocks it.
- Another container on the host reaches Ollama and pulls or deletes models. Ollama is only on the compose network and `127.0.0.1`.

## OWASP items in scope
- ASI04 (agentic supply chain): dependency, image and licence controls; new images pinned by digest and licence-checked (Valkey BSD-3, Kafka and SeaweedFS Apache-2.0).
- LLM03 2026 (supply chain): the same controls. Model weights are covered in Sprint 013.
- LLM10 2026 (unbounded consumption): Ollama is opt-in by profile.
- Other ASI items: none. No agent behaviour changes.

## Residual risks
- The gate trusts package metadata. A package that lies about its licence passes.
- Path filters can skip a job when a change touches an unlisted path. The filters list backend roots on purpose.
- Kafka in the `streams` profile has no SASL or ACLs until 022. It is bound to localhost meanwhile.
- `127.0.0.1` binding does not stop other local users or processes on the same host.
