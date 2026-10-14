# Sprint 020: Threat model

## Assets
- Source database credentials (`refco_cdc`), Kafka SCRAM credentials, the replication slot.
- Change streams on `cdc.*` topics (they hold PII from CRM and HR tables).
- Tenant datasets written by the sink, and their offsets.

## Trust boundaries crossed
- Source Postgres to Debezium (replication protocol).
- Debezium to Kafka to the sink (messages are untrusted input).
- The sink, which starts with no tenant, into one tenant's catalog.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A message claims another tenant (field, header or `source.db`) and writes its data | Spoofing | Tenant only from `cdc_source_for_topic`; `source.db` must match the registration or the batch is quarantined | `test_cdc_tenancy.py::test_spoofed_source_quarantined` |
| T2 | A client without credentials, or the wrong user, produces to `cdc.*` | Spoofing | SASL/SCRAM, `allow.everyone.if.no.acl.found=false`, prefix ACLs per user | `scripts/verify/cdc.sh` ACL step (`evidence/kafka-acl.txt`) |
| T3 | Connect REST API used to read configs or add a connector | Elevation of privilege | Port 8083 not published; only the one-shot register job on the network | `test_compose_cdc.py::test_connect_port_not_published` |
| T4 | Source password visible in connector config, env or logs | Information disclosure | File config provider; secrets mounted read-only; API returns no connection detail | `test_cdc_secrets.py::test_no_secret_in_api_or_logs`, verify step on `GET /connectors/.../config` |
| T5 | Replication role reads or writes more than listed tables | Elevation of privilege | `LOGIN REPLICATION`, SELECT on listed tables, filtered publication, autocreate off | `test_cdc_source_setup.py::test_role_and_publication_scope` |
| T6 | Replay after a crash double-applies or loses changes | Tampering | Offsets and LSN state in the same DuckLake transaction; seek on start | `test_cdc_sink_replay.py::test_kill_between_write_and_commit` |
| T7 | A crafted schema change drops or retypes a column | Tampering | Only nullable add-column applied; others quarantine and pause | `test_cdc_schema_changes.py::test_narrowing_quarantined` |
| T8 | Sink outage lets WAL fill the source disk | Denial of service | Slot lag metric and alert; runbook to drop the slot | `test_cdc_sink_apply.py::test_slot_lag_metric` |
| T9 | Flood of messages exhausts sink memory | Denial of service | `CDC_BATCH_MAX_RECORDS`, bounded batch window | `test_cdc_dedupe.py::test_batch_bounds` |
| T10 | PII from change payloads lands in logs or quarantine rows | Information disclosure | Logs carry offsets and codes; raw batch only in the tenant's object prefix | `test_cdc_secrets.py::test_no_payload_in_logs` |

## Abuse cases
- A tester publishes a forged Debezium envelope to `cdc.<tenant A source>` with `source.db=other_db`. Refused by ACL; if produced by Debezium itself, quarantined.
- The sink is stopped for a long time. The slot lag alert fires; the runbook explains a resnapshot.

## OWASP items in scope
- OWASP Top 10:2025 A01 Broken Access Control (T1–T3) and A02 Security Misconfiguration (open Connect port, `allow.everyone`).
- ASI: none. No agent touches the change stream. ASI04 supply chain covered by image digests.
- LLM Top 10: none. No model is called.

## Residual risks
- Kafka traffic is not encrypted inside the compose network. TLS is out of scope; the network is local only.
- `CDC_TOPIC_RETENTION_HOURS` is a placeholder until the owner confirms it.
