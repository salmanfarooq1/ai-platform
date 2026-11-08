# Sprint 012: Contract review

**Disposition: ready for implementation after Sprint 011 acceptance.** No Sprint 012 acceptance item is signed off by this review.

The Architect reviewed the current recording, chain, gateway, auth, worker, identity and composition paths. The dedicated Builder independently audited the pack twice without changing product files. The resulting decisions are in `architect-disposition.md` and aligned with the requirements, blueprint, brief, acceptance, threat model and program conventions.

| Readiness issue | Selected resolution |
|---|---|
| Conflicting stage order and credential precedence | Principal then module; retain original route scope and run-grant dependencies |
| Action map misses agent reads, sandbox models and MCP opening | Trusted registry-owned route attribution checked with the action map |
| Optional M2 could disable mandatory recording | Always-real decision sink and evidence lookup; raising sink only for failure tests |
| Port fields vague or inconsistent with NOT NULL columns | Exact asynchronous, gateway-independent value contracts; action/stage/reason are strings |
| V1 signatures could include new defaults | Explicit 13-field v1 projection, unchanged JSON/timestamp encoding; version-aware export and offline verification |
| Extensions could mutate or change through JSONB | Deep-owned immutable values, recursive validation, canonical UTF-8 byte bound |
| Single-tenant checks could miss existing tenants or race | Narrow privileged startup boolean and owner transaction lock around count/create; RLS retained |
| Removing handlers still claims or expires disabled jobs | Filter claim and expired-lease maintenance by registered kinds; revoke unfiltered app overload |
| Eager composition loads disabled graphs/SDKs | Dotted enabled factories and fresh-process import checks |
| Metadata requires a data scope that valid agent/auditor/writer keys lack | New system.read grants platform metadata only to every recognized scope; no old data/model/audit grant widens |
| Command Palette caches unfiltered navigation separately | Sidebar and palette share session-keyed filtered nav, hidden until optional module metadata loads |
| Container COPY list omits the new evidence package | Add evidence explicitly and prove Gateway-only boot/recording from the final image |
| Lineage drop/count conflicts with future spool | Drop/count explicit in 012; durable spool required before 022 producers, consumed in 025 |
| Test import-only wording conflicts with new contracts | Preserve pure-move checkpoint; later fixture/signature changes retain assertions and add intended-behavior coverage |
| Historical migration test expects old claim privilege | Target its historical revision and separately test the new revocation at head |

Implementation must still prove every acceptance item with captured command evidence, including full regression tiers and all five real-lifespan edition boots. The migration number and regression baseline are taken from the finally accepted Sprint 011 result. No commit, push or merge was run.
