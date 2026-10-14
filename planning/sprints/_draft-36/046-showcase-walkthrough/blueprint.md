# Sprint 046: Blueprint
- **Contract:** no API change. OpenAPI snapshot must not drift.
- **Journeys** (from `sprint-map.md`, on the reference company):
  | Script | Journey | Profiles |
  |---|---|---|
  | `m0.sh` | A model call on a local model is denied by policy; the receipt names the model digest; a module is switched off | core, models |
  | `ma.sh` | Finance and CRM data land, become certified products with contracts and quality scores; analyst requests with a purpose; steward approves; analyst reads masked rows; lineage shows every step | core, lake, cdc |
  | `mb.sh` | "What was Q3 gross margin by region?" answered in a sandbox, naming metric, snapshot and masked columns, then replayed; the finance dashboard shows two viewers different numbers with a receipt per tile; a weekly PDF report reaches each recipient with only what they may see; a poisoned invoice PDF cannot leak data. Runs on the Full edition (it needs the agents, dataplane and insights modules) | core, lake, models |
  | `mc1.sh` | An SSO user acts through a delegated run identity; MCP and A2A calls are governed under the OPA engine | core, models, identity, policy |
  | `mc2.sh` | A salary question needs a human approval; the approver sees system evidence; guard models and governed memory are on | core, lake, models, guard |
  | `md.sh` | An auditor exports a signed evidence pack for one system and one quarter and verifies it offline, with a replay of "why was this allowed" | core, trust |
  | `me.sh` | Each edition installs from wheels and passes its smoke set (Sprint 045 scripts) | none beyond each edition's set |
- **Script rules:**
  - `SHOWCASE_MODEL=fake|local`. `fake` uses the e2e fakes (`scripts/e2e/serve.py`) and is what CI runs. `local` uses Ollama and the pinned models.
  - State (keys, ids, packs) goes to a git-ignored `.showcase/` directory. Keys are never printed after creation.
  - Compose runs under the project name `showcase`. Teardown touches only that project.
  - `mc.sh` from Sprints 034 to 039 is split into `mc1.sh` and `mc2.sh`, so no journey runs identity, policy, lake and guard at once inside the 12 GB WSL limit. `OLLAMA_MAX_LOADED_MODELS=3` is set only by the `guard` profile.
  - Each step prints `ok` or `FAIL`, the command, and the evidence (decision id, receipt check, pack verify line).
- **Playwright:** `ui/e2e/showcase-m0.spec.ts` to `showcase-me.spec.ts` (MC has `showcase-mc1.spec.ts` and `showcase-mc2.spec.ts`; ME checks the Platform > Modules page per edition boot in CI). Each follows the same steps through the console as the script does through the API, where a UI exists.
- **Landing:** update `ui/src/landing/claims.ts`, `story-data.ts`, `example-data.ts`, `how-it-works-page.tsx`. New may-claim items in `CONTENT_STYLE.md` only for built and tested features, each naming its test. Remove items from the must-not-claim table that are now built. Example data stays labelled as examples. `landing.spec.ts` checks the new sections.
- **Docs:**
  - `README.md`: what it does, the five editions, the chain in one diagram, quick start pointing at `all.sh`.
  - `docs/getting-started.md`: fresh laptop path: WSL and Docker Engine, `scripts/preflight.sh`, `.wslconfig`, clone, `poetry install`, stores, models pull, identity setup, first journey.
  - `docs/architecture.md`: modules, ports, editions, request path, evidence path.
  - `docs/adr/README.md`: rows for ADR-0013 to ADR-0031.
  - `docs/showcase.md`: each journey, its command, the expected output and the memory per profile set.
- **Data, ports, gateway, events:** none.
- **CI:** a `showcase` job runs `all.sh` with `SHOWCASE_MODEL=fake` and the Playwright showcase specs. Heavy profiles that do not fit a CI runner run nightly; the job states which.
- **Tests:** shellcheck on the scripts; a test that each journey in `sprint-map.md` has a script and a spec; a docs link test over the changed docs; `copy-check`; `test_showcase_mc_profiles_split` (`mc1.sh` and `mc2.sh` declare their profile sets, and no script starts identity, policy, lake and guard together); `test_adr_index_complete` (rows for ADR-0013 to ADR-0031).
