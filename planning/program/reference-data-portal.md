# Reference: the earlier GCP data portal

The earlier project (a data mesh catalog on GCP: FastAPI, React, Keycloak, Dataplex, BigQuery, Analytics Hub, Firestore) is one input. It is not the design. Our design comes from the research and the platform we already have. This file lists what we take, what we change, and what we avoid.

## Ideas we take
| Idea | Where it lands |
|---|---|
| A product lifecycle as an explicit state table, with an audit event on every transition | 023 |
| Auto-checks as a registry of named functions (missing owner, missing classification, PII not classified, no lineage, broken SLO) | 023 |
| Policy as a versioned document, with the approver group copied onto each request when it is made | 024, 018 |
| "Approved" and "access granted" as separate states, with a grant queue between them | 024 |
| Reads run with the caller's own scoped identity, never with a broad platform identity | 021, 024, 020 |
| Auto data quality: find existing checks, else create a baseline set, then a human approves | 023 |
| A merged view of product lineage and physical lineage | 025 |
| Downloads leave through short-lived signed URLs, not through the API process | 024 |
| Audit search and export | 030 |
| A data agent that inherits the user's credentials, never its own elevated identity | 027 |

## What we change
| In the portal | In our platform |
|---|---|
| Dataplex entries and aspects | Postgres tables with JSON Schema validated aspect types, ODPS and ODCS documents |
| Dataplex data quality scans | Contract-driven checks on DuckDB, auto-profiling drafts |
| BigQuery | DuckDB on DuckLake, through the gateway |
| Analytics Hub listings and subscriptions | Listings, requests and grants in Postgres, enforced by rewriting each query |
| Firestore workflow state | Postgres with row-level security |
| Cloud Logging audit | Hash-chained decision records with signed receipts |
| GCP Workload Identity Federation | Keycloak token exchange (RFC 8693) and run identities |
| Background loops inside the web process | The existing job queue and workers |
| Gemini through a GCP MCP server | Local models through Ollama, our own governed MCP tools |

## What we avoid (found in the portal review)
These become explicit tests in the sprints that touch the same area.
- TLS verification turned off for identity calls. Our rule: never, in any mode. (020)
- Falling back to a code exchange when the OIDC state check fails. Our rule: fail closed. (020)
- Accepting unsigned or symmetric tokens in debug mode. Our rule: no debug bypass. (020)
- A SQL guard built on a keyword blocklist, and a query cache shared across users. Our rule: parse the SQL, allow only reads, key every cache by principal and grant. (024, 025)
- Sharing a product with no approval step. Our rule: every grant comes from an approved request. (024)
- Granting access with the platform's own broad identity, with a fallback to a default dataset. Our rule: no fallback, deny on any doubt. (024)
- Sensitivity never set, so every request is auto-approved. Our rule: a product without a classification cannot be certified or listed. (023)
- Group names that differ between the identity provider and the code. Our rule: one mapping file, tested. (020)
- Checks that never re-run, and certification that ignores check results. Our rule: scheduled re-evaluation, and certification blocked by failed blocking checks. (023)
- Default passwords for new users. Our rule: none; users come from the identity provider. (020)
