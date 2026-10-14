# Sprint 012: Threat model
## Assets
- Data in Postgres, the cache, the Kafka topics and the object store bucket.
- Service credentials (Postgres, S3 keys, Grafana admin).

## Trust boundaries crossed
- The local network (LAN, WSL mirrored networking) to the published container ports.
- The host to the containers.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A host on the LAN reaches Postgres, Valkey, Kafka, SeaweedFS or Ollama on a published port. | Information disclosure | Every published port bound to `127.0.0.1`. | `test_compose.py::test_no_port_on_all_interfaces`; `evidence/ports.txt`. |
| T2 | A service starts with a well-known default password. | Elevation of privilege | Credentials from the environment; local-only defaults documented; no default for S3 keys. | `test_compose.py::test_no_literal_secret_in_compose` (no secret-looking value except named local defaults). |
| T3 | A cache index error is treated as success, so tenant filters are missing. | Information disclosure | Only "already exists" is tolerated, and the existing field check still recreates an index that lacks `tenant_id`. | `test_already_exists_text_of_both_servers`; cache contract tenant-isolation cases on Valkey. |
| T4 | A dependent service starts before its store is ready and runs half-configured. | Denial of service | Healthchecks and `condition: service_healthy`. | `test_compose.py::test_dependencies_wait_for_health`. |
| T5 | A presigned URL works longer or wider than meant. | Information disclosure | The contract checks expiry and that the URL names one key. | `scripts/verify/seaweedfs.sh` presigned cases. |
| T6 | An image changes under a tag. | Tampering | Digest pins (from 011) for every new image. | `test_compose.py::test_images_by_digest`. |

## Abuse cases
- A process on the LAN tries `redis-cli -h <host>` and reads cached answers. Blocked by the localhost binding.
- Another container on the host reaches Ollama and pulls or deletes models. Ollama is only on the compose network and `127.0.0.1`.

## OWASP items in scope
- ASI04 (supply chain): new images pinned by digest and licence-checked (Valkey BSD-3, Kafka and SeaweedFS Apache-2.0).
- LLM10 2026 (unbounded consumption): Ollama is opt-in by profile, so it does not use memory by default.
- Other ASI items: none. No agent behaviour changes.

## Residual risks
- Kafka in the `cdc` profile still has no SASL or ACLs. That comes in Sprint 020. It is bound to localhost meanwhile.
- `127.0.0.1` binding does not stop other local users or processes on the same host.
