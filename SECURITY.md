# Security

This page describes what the platform protects, how it protects it, and how to report a problem.

## Reporting a problem
Report a suspected vulnerability privately to the repository owner on GitHub, using private vulnerability reporting under the repository's Security tab where it is enabled. Do not open a public issue. Include the affected route or component, the steps to reproduce it and the impact you expect. You will get an acknowledgement, and a fix or a plan, as soon as the report is confirmed.

## What is protected, and how

| Concern | Protection |
|---|---|
| **Who is calling** | Every `/v1` route except health and sign-in needs a credential: an API key (only a hash of the secret is stored), a JWT with a fixed algorithm list, or a web session cookie. The tenant comes only from the credential, never from a header, body or query |
| **Tenant isolation** | Postgres row-level security, forced on every tenant-owned table. The app connects as a role that cannot bypass it, and refuses to start otherwise. A missing tenant setting returns no rows |
| **What a caller may do** | Scopes per route, plus `gateway.enforce()` on every model, tool and knowledge-base call. It checks policy, guardrails, rate, token budget and daily cost. Authority only narrows: an agent or tool never gets more than its caller |
| **Failure** | Fail closed. If a check cannot run, the call is denied. If the decision record cannot be written, the call answers 503 and does not run |
| **Audit** | Each governed call writes a decision record, chained per tenant and signed as an Ed25519 receipt. Records hold the SHA-256 of the input, never the text. Editing or removing a record breaks the chain |
| **Agents** | The agent acts only through the gateway. A sandboxed run can reach only the platform, writes only its work directory, runs under CPU, memory and time limits, and holds a short-lived token bound to its own run. Tool arguments are checked against the tenant's schemas |
| **Browser** | The browser never holds an API key. Sessions use an HttpOnly, SameSite=Strict cookie and a CSRF token on writes. Sign-in is rate limited per client address |
| **Secrets** | Read from the environment only, validated at start and held as secret values, so they never appear in logs, errors or API responses. Keys and tokens are shown once when created |
| **Logs, events and metrics** | They carry no input text, no secrets and no tenant data in metric labels. Error responses never include exception text |
| **Supply chain** | Dependencies are locked with hashes (`poetry.lock`, `package-lock.json`). Optional runtimes (the OpenShell SDK and packages) are pinned by version and checksum |

## Operating securely
- **Separate roles.** Keep `DATABASE_URL` on the `gap_app` role and use the owner role only for migrations and the admin CLI.
- **Protect the signing key.** Keep `RECEIPT_SIGNING_KEY` in a secret store, and list old public keys after a rotation.
- **Revoke leaked keys** with `scripts/admin/identity.py revoke-key <prefix>`. Their sessions and run tokens end too.
- **Close `/metrics`.** Leave `METRICS_PUBLIC` off outside local mode.
- **Know the limits.** The receipt chain is tamper evident inside Postgres, not tamper proof. An attacker with the owner role and the signing key could rewrite it. [ADR-0012](docs/adr/0012-receipts-and-hash-chain.md) explains the trust model.
