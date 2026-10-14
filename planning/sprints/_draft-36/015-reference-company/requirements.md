# Sprint 015: Reference company. Requirements

Data and docs, Kernel. One fictional distributor used by every showcase, test and eval from here on.

## Scope
1. A fictional distributor, with functional names only (no real brands).
   - Finance: invoices, ledger, budgets.
   - CRM: accounts, contacts (with PII), opportunities.
   - HR: salaries (restricted).
   - Documents: invoice and contract PDFs generated from the data.
   - A written data policy in plain language.
2. Deterministic generators in `data/reference-company/`.
   - Seeded, with a small and a medium size.
   - A data dictionary.
3. A source database.
   - Postgres `refco_source` in the compose profile `lake`, seeded from the generators.
   - A change generator script for the CDC tests of later sprints.
4. Personas and keys.
   - Producer (finance engineer), steward, consumer (analyst), operator, auditor, agent developer.
   - Created with `scripts/admin/identity.py`, with a policy file per persona.
5. Showcase skeleton.
   - `scripts/showcase/m0.sh` runs the M0 journey, and a Playwright test covers it.
   - `docs/showcase.md` lists the journeys per milestone.

## Out of scope
- Loading the data into the lakehouse (017). Logical replication settings and Debezium (020).
- Any route, migration or new UI page.

## Nav placement
No UI change. The Playwright test uses existing pages (Decisions, Platform > Modules).

## Questions this sprint closes
- None from the open list. The persona policy question below goes to `planning/QUESTIONS.md`.
