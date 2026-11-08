# UI delivery by sprint

The owner's instruction is binding: deliver every applicable UI change in the sprint that delivers its scope. This map summarizes the existing requirements; it does not defer missing UI or replace each sprint's acceptance pack. The Architect checks the actual accepted prerequisite code before finalizing each contract.

Every affected journey uses the real API, enforces the same permissions and module visibility, and covers loading, empty, error and denied states. Include keyboard access and reduced motion where relevant, update generated API types and design documentation, and capture an end-to-end browser test before accepting the sprint. Do not leave working backend functionality inaccessible when its intended users need a console flow.

| Sprint | UI delivered or verified within that sprint |
|---|---|
| 011 | Existing landing motion, font assets, reduced motion and narrow-screen behavior; all existing browser journeys. |
| 012 | Platform > Modules; session-aware filtering shared by sidebar, command palette, Ask Agent controls and direct optional routes; version-aware basic receipt journeys remain available in Gateway edition. |
| 013 | Existing Decisions and receipt views display resolved model/provider, region, immutable identity and the per-stage list from the signed record. No new page is required. |
| 014 | Reference-company journeys through existing Decisions and Modules pages; no new page is required. |
| 015 | Restore and lifecycle drills verify the restored existing console and receipt journey. Infrastructure commands do not require a new console page. |
| 016 | Governance > MCP registry approval/reapproval flows and Governance > Agents registration and stop controls; Gateway Test sends a real request and shows reached stages from the signed record; showback by cost centre. |
| 019 | Governance > Guardrails library, ordered bindings and activity counts from decision records; approval queue and Oversight log; run Stop/Override; shared inbox behavior. |
| 020 | Platform > Identity and OIDC sign-in; delegation chain on agent runs. |
| 017 | Evidence > Receipts lookup, signature/key/attestation status and verification; Evidence > Audit search and export. |
| 018 | Governance > Policies, test bench and what-if; replay from Evidence > Decisions. |
| 021 | Data > Connections add/test and Data > Datasets list/preview with storage location. |
| 022 | Dataset snapshots/query-as-of; Pipelines definitions, runs, logs, run/backfill; Streams/CDC freshness. |
| 023 | Data > Products creation/import/contracts/certification and Data > Quality. |
| 024 | Marketplace, My access and governed Data query; access-request approvals. |
| 025 | Data > Lineage and the metrics panel in Workspace > Ask. |
| 026 | Document review queue, Library chunk/ACL views, retrieval and grounding evaluations. |
| 027 | Workspace > Ask and connection-specific integration suggestions with approve/reject. |
| 028 | Agent registry/templates/autonomy controls, run breakers/alerts, Memory and Platform > Observability. |
| 029 | Insights Metrics, Explore, Dashboards, Reports and their shared inbox integration. |
| 030 | Evidence Packs and Frameworks. |
| 031 | Platform > Deployment with actual drill results and key/secret status. |
| 032 | About version/edition/SBOM, supported landing and How-it-works claims, every milestone journey and accessibility across every shipped page. |

The 032 accessibility audit verifies the completed product. It does not postpone accessible implementation or applicable UI from earlier sprints. An out-of-scope trace-store UI in 028 remains out of scope; its specified observability status page still ships in 028.
