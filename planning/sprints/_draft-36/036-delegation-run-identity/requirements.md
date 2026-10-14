# Sprint 036: Delegation and run identity. Requirements

A vertical slice in M1 Gateway and M3 Agent Runtime: an agent run acts for a user through a delegation token that only narrows, with a run identity and a chain shown on every decision.

## Scope
1. **Spike first.** Does Keycloak `26.7.4` standard token exchange (v2) accept an `actor_token` and emit a nested `act` claim? Nested delegation needs the preview feature `--features=token-exchange-delegation`. The spike turns it on in a throwaway profile only. Record the result in `evidence/spike-token-exchange.md`.
2. **Delegation tokens (decided 2026-10-11).**
   - Default: the platform mints them, as it already mints run tokens. They carry the `act` chain. This path is built and tested in this sprint whatever the spike shows.
   - Keycloak token exchange issues them only if the spike passes **and** nested delegation is a supported (not preview) Keycloak feature at sprint start. Preview features never run in the default stack.
   - Both issuers sit behind one `DelegationIssuer` port with one contract suite, so a later switch to Keycloak needs no change elsewhere.
3. **Rules, each with tests.**
   - `may_act` is checked before any exchange.
   - The audience is limited to one downstream per token.
   - The lifetime is at most the run's.
   - Each hop only narrows scopes (strict rule 5). A widening request is refused.
4. **Run identity.**
   - SPIFFE-format run ids: `spiffe://<trust-domain>/tenant/<tenant_id>/run/<execution_id>`, without SPIRE.
   - SPIRE is documented as an optional later step.
5. **Chain in records.** The delegation chain is stored on every decision a run causes (record v2 extension) and shown in the run view. ADR-0025.
   - The chain goes into `PolicyInput`, with decision-table rows for both engines.
6. **Report runs (029).** A report or alert run is a delegation: `sub` is the recipient, `act` is `job:insights.report.run`. The recipient's `may_act` names `insights.report`.

## Out of scope
- SPIRE, workload attestation and X.509 SVIDs.
- A2A identities (Sprint 037).
- Replacing run tokens. The run token stays the sandbox's credential to the gateway.

## Nav placement
Governance > Agent runs: a "Delegation chain" panel on the run view, and the chain on each decision row.

## Questions this sprint closes
- The delegation issuer: platform-minted by default (decided 2026-10-11, `planning/DECISIONS.md`). The spike result is recorded there too.
