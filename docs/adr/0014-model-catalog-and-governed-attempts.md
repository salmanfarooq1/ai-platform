# ADR-0014: Model catalog and governed attempts

**Status:** Accepted

## Context

Model calls can retry, fall back, or target hosted providers. The gateway must identify and record the concrete physical route that each request uses, while local model aliases remain pinned to reviewed artifacts.

## Decision

Every physical model attempt passes through `gateway.enforce()` and receives its own recorded decision before provider I/O. SDK adapters make one request only. Model integrations use the typed, SDK-free ports in `ports/models.py`; route limits use `ModelLimitStore` in `ports/model_limits.py`.

The provider register (`providers.register.toml`) describes hosted provider behavior and processing scopes. `models.lock` pins local model aliases to reviewed digests. Vector provenance is `<alias>@<digest>` for local models or `<alias>@<provider_model_id>` for hosted models. Local inference uses `DEPLOY_REGION` as its processing region. The optional `verifier_must_be_local` policy field denies a hosted verifier.

Each route fingerprint has a Valkey-backed circuit breaker. A per-tenant Valkey lease limits concurrent physical attempts and expires after the configured call timeout plus its margin. The local CPU Compose profile initializes the locked model store, then serves it read-only.

## Consequences

Retries and fallbacks create separate decisions and cannot inherit the primary attempt's authorization. Catalog entries, digests, provider model identifiers, and processing scopes are part of review and deployment. The CPU profile remains local and does not add a GPU requirement.

## Alternatives considered

- **Resolve aliases only at application startup:** rejected because a tag change could alter the route after review, and a fallback still requires its own authorization record.
- **Let SDK retries remain implicit:** rejected because each physical request would lack a separate decision.
