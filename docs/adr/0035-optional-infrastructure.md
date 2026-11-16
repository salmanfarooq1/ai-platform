# ADR-0035: Optional infrastructure behind ports

Status: Accepted (re-plan 2026-11-08, owner agreed)

## Context
The plan for sprints 013 to 032 added many services to the default stack: Trino, OPA, Debezium with Kafka Connect, Kafka and Keycloak. Each one costs memory on a 16 GB laptop, an upgrade path, a security surface and a support burden for a client install. Most clients already run their own identity provider, and most POC data fits in DuckDB. We want fewer moving parts with the same quality, and we already have the pattern to do it: ports, adapters and one composition root (ADR-0005).

## Decision
1. **Required services.** Only Postgres, Valkey, the API and the worker are required. Every other service is optional.
2. **Optional means behind a port.** An optional service has a port in `ports/`, a default adapter that needs no extra service, and one setting read only in `adapters/registry.py`.
3. **Parity test.** The same contract suite runs on the default adapter and on each option. An option is not "supported" until it passes. The option's suite runs in a CI profile or nightly, not on every PR.
4. **Settings.**

   | Setting | Default | Option | Sprint |
   |---|---|---|---|
   | `QUERY_ENGINE` | `duckdb` | `trino` (built when a client needs it) | 021 |
   | `POLICY_ENGINE` | `python` | `opa` | 018, 030 |
   | `EVENT_BUS` | `outbox` | `kafka` | built |
   | `OBJECT_STORE` | `local` | `s3` | built |
   | `IDP` | `oidc` (any standard provider) | — | 020 |
   | `AGENT_RUNTIME` | `openshell` (pinned version) | `docker`, `gvisor` | 027 |

5. **Cuts.**
   - No Debezium. Change capture uses Postgres logical replication or a dlt incremental source, with a replication-slot WAL-growth monitor (ADR-0017, retitled).
   - Keycloak is a test issuer for CI and nightly only. We ship an OIDC client and SCIM 2.0, and resolve the Entra group overage through Microsoft Graph.
   - The gateway has two modes: embedded and standalone proxy. Sidecar comes later.
   - LiteLLM is used as a library, never as its proxy. Presidio and Docling run in process.
6. **Editions sold.** Gateway, Gateway + Data, and Full. The five module sets from Sprint 012 stay as technical CI profiles.

## Consequences
- The default install stays near 2 GB for `core`, and a POC needs no Java services.
- DuckDB carries federation by default. Sprint 021 must first prove a real Postgres plus SQLite join under the locked settings, or this decision is reopened.
- The Python policy engine is the only engine in the default path. OPA parity (030) becomes a client option, not a dependency.
- Some clients will ask for Trino, Kafka or OPA. Each request is an adapter against an existing contract suite, not a re-design.
- Every new service proposed in a sprint pack must name its port, setting and parity test, or the Architect rejects it.

## Alternatives considered
- **Keep the full stack as default.** Rejected: too heavy for a laptop POC, and most services duplicate what Postgres or DuckDB already do at POC scale.
- **Drop the options entirely.** Rejected: large clients run Trino, Kafka or OPA already, and integration first (rule 12) means we govern what they have.
- **Debezium Server without Kafka.** Rejected for now: still a Java service to run and patch, while logical replication covers the POC need.
