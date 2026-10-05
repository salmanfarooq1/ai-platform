# Sprint 009: QA and code review

The QA agent returned this as text, and the Architect saved it. The QA agent ran 129 targeted tests, and all passed. It did not run the live OpenShell script; it checked the live claims against the evidence files.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass | The contract suite runs against the fake sandbox. The only skips are the standing 10 live-MinIO skips. The Architect confirms that `check_skips.py --expect 10` is the skip policy. |
| A2, A3, A5 | pass | Fake sandbox and live evidence |
| A4 | partial | The read fails live, but OpenShell logs no event for it (Q37) |
| A6 | pass | Principal-scoped merge. A foreign run gets 404. |
| A7 | pass, one setup | The runbook lists what is not verified |

## Findings
**High:** none.

**Medium**
- **M1:** on the sandbox tool route, `decision_unrecorded` returns 403 `policy_denied`, not 503.
- **M2:** the keys of `tool_arguments` are not checked against the known tools, so a typo protects nothing.
- **M3:** a tenant's schema `pattern` can backtrack catastrophically and stall the event loop.

**Low**
- **L1:** a leaked run token can write one deny row per request, before the rate limit applies.
- **L2:** the agent's stdout (citations, usage, confidence) is stored as fact.
- **L3:** the `message` of `network_denied` events relies on pattern redaction.
- **L4:** the bearer token crosses the Docker bridge over plain HTTP.
- **L5:** the base images in the runbook are not pinned by digest.
- **L6:** revoking the API key that started a run leaves the run token live.

## Architect disposition
**Builder fixes, each with a test**

| Finding | Fix |
|---|---|
| M1 | `decision_unrecorded` and `internal_error` map to the standard 503 on the sandbox routes. |
| M2 | `set-policy` refuses unknown tool names in `tool_arguments`. |
| M3 | `set-policy` refuses `pattern`, `patternProperties` and `format`-driven regex in tool schemas. Use enums, lengths and types instead. Validation also runs off the event loop with a time limit, and a timeout is a deny. |
| L1 | Out-of-run token uses write at most one deny row per token and path per minute. Further uses are still refused. |
| L2 | The stored result and the runs API mark the agent's citations, usage and confidence as `agent_reported`. Booked usage stays gateway-measured. |
| L3 | `network_denied` keeps only host, port and reason. |
| L6 | A run token is refused once the API key that minted it is revoked. |

**Accepted and documented in the runbook and RISKS**

| Finding | Reason |
|---|---|
| L4 | The bridge is host-local, and the token's lifetime is short. TLS to the gateway is a hosting item. |
| L5 | Digests can't be fetched here. The runbook tells the operator to pin by digest on first pull. |
