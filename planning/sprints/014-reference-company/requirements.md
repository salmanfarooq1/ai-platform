# Sprint 014: Reference company. Requirements

Platform and docs, Kernel. One fictional distributor used by every showcase, test and eval from here on, plus the M0 journey script.

Source: old 015, plus new scope (client-shaped variants, cloud showcase).

## Scope
1. **A fictional distributor**, with functional names only (no real brands).
   - Finance: invoices, ledger, budgets. CRM: accounts, contacts (with PII), opportunities. HR: salaries (restricted).
   - Documents: invoice and contract PDFs generated from the data, and a written data policy in plain language.
2. **Deterministic generators** in `data/reference-company/`.
   - `generate.py --size small|medium --seed 42 --out DIR`: CSV per table, PDFs and `manifest.json` (file, rows, SHA-256). Sizes: small (50 accounts, 1,000 invoices, 40 employees) and medium (2,000 accounts, 100,000 invoices, 400 employees).
   - Tables: `fin_invoices`, `fin_invoice_lines`, `fin_ledger_entries`, `fin_budgets`, `crm_accounts`, `crm_contacts`, `crm_opportunities`, `hr_employees`, `hr_salaries`.
   - A data dictionary with a classification per column (`public`, `internal`, `pii`, `restricted`). `checksums.json` holds the expected hash per size and seed.
   - Safe values only: emails on `example.com`, `.org` and `.net`, a reserved phone range, `TEST-` tax and bank ids. `deny_list.txt` names brands and real domains that must never appear.
3. **Client-shaped variant (new).**
   - `generate.py --schema FILE` emits the same kind of data in the shape of a client's schema file (tables, columns, types, keys). Faker (MIT) fills the values and keeps keys consistent.
   - The schema file is a small documented JSON format. A client's real data never enters the repo.
   - SDV is rejected (Business Source License).
4. **Source database with a change generator.**
   - Postgres `refco_source` in compose profile `lake`, seeded by `load_source.py`. Read-only role `refco_reader`.
   - `change_generator.py --seed S --steps N` makes a fixed run of inserts, updates and deletes for the stream tests of 022.
5. **Personas and keys.**
   - Producer, steward, consumer (analyst), operator, auditor, agent developer. One JSON file each, with scopes and a tenant policy.
   - `scripts/showcase/setup_personas.sh` creates tenant `refco` through `scripts/admin/identity.py`. Keys go to a git-ignored `.showcase/keys.env`, never to logs.
6. **Showcase skeleton for M0.**
   - `scripts/showcase/m0.sh` and `ui/e2e/showcase-m0.spec.ts`: a policy leaves out the local chat model, the consumer is denied, the auditor checks the receipt (model name and digest, signature), and `ENABLED_MODULES=gateway` shows `agents` off.
   - The cloud steps (`poc up`, backup, `poc down`, restore) are added by 015. Until then they print SKIP, never PASS.
   - `docs/showcase.md` lists the journeys per milestone (M0, MG, MD, MA, ME).

## Out of scope
- Loading data into the lakehouse (022) and the stream setup (022).
- Any route, migration or new UI page.
- Real client data, or a client's secrets.

## Nav placement
No UI change. The Playwright test uses existing pages (Decisions, Platform > Modules).

## Questions this sprint closes
- None from the open list. The persona policy question goes to `planning/QUESTIONS.md`.
