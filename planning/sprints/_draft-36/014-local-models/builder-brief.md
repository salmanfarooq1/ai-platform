# Sprint 014: Builder brief
You are the Builder for Sprint 014 in /home/ubuntu/ai-platform, on branch `sprint/014-local-models`. Infrastructure, Kernel and M2: local models by default, `models.lock`, and the model digest in decision records. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, ADR-0005, ADR-0012, ADR-0013.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `planning/program/stack.md` (Models section and memory budget) and the Sprint 013 report.
- `core/settings.py`, `config.py`, `adapters/litellm_chat.py`, `adapters/litellm_llm.py`, `adapters/registry.py`, `evidence/extensions.py`, `tests/fakes.py`.

## Build
Order: port and fake with the contract suite; `models.lock` and `check_lock.sh`; settings and defaults; gateway extension and reason; compose and the verify script; nightly job; docs. Write a short plan in `build-log.md` first.

## Tests
- **Baseline:** the numbers in Sprint 013's report.
- CI and pytest use the fake LLM and `FakeModelCatalog`. The network guard fixture stays on.
- The stub Ollama server in the contract suite is in-process (no real network).
- Live checks go in `scripts/verify/ollama.sh` and its evidence, never in a skipped pytest.

## Notes from the Architect
- **Code facts:**
  - The local chat default is in `core/settings.py` `_LLM_MODEL_DEFAULTS` (`gemini/gemini-3.5-flash-lite` for `local` and `public-preview`), not in `config.py`.
  - `config.py` `LLM_CONFIG["fallbacks"]` is `["ollama/qwen2.5"]` in local mode and `["ollama/llama3"]` otherwise.
  - A hosted mode refuses to start for a configured model with no entry in `MODEL_PRICING` (Sprint 008). Add every lock model at 0.0.
  - Chunks record `embedding_model`. Keep the embed setting text `ollama/nomic-embed-text` exactly, or every stored vector becomes stale. The lock maps that name to its digest.
  - The `ollama` service and `models` profile exist since 012, bound to `127.0.0.1`.
- **Pins:** `ollama/ollama:0.34.4` by digest (011). Pull each model, read its digest, and save name, digest, size and source in `evidence/pins.txt` and `models.lock`. Licences per `planning/program/stack.md` (Apache-2.0 for qwen3 and nomic-embed-text). Re-check them on the model pages.
- **Measured latency:** run `scripts/verify/ollama.sh --bench` on the build machine. Write the numbers and the CPU into `docs/operations.md`. If no GPU is present, write "not measured here" for the GPU profile.
- **No thinking mode:** the 4B instruct build is used on CPU. Do not switch to a thinking model.
- **No migration.** The extension uses the 013 `extensions` map.
- **ADR-0014:** local by default, hosted providers as optional adapters, licence gate covers models.

## Run
```bash
poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
poetry run lint-imports
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/014-local-models/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/014-local-models/evidence/pytest-int-e2e.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
docker compose --profile models up -d ollama ollama-pull
scripts/models/check_lock.sh
scripts/verify/ollama.sh
scripts/verify/ollama.sh --bench
cd ui && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs. Hosted model keys stay env vars, unused by default.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1 to A6, A-sec, A-mem) with links to `evidence/`
- test numbers and the delta against Sprint 013's report
- "No migration"
- measured tokens per second and memory
- deviations and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md`: contract (`ports/models.py`, `feat(models)`), code (`adapters/`, `core/settings.py`, `config.py`, `gateway/`, `evidence/extensions.py`, `models.lock`, `feat(models)`), tests (`test(models)`), ops (`docker-compose.yml`, `scripts/`, `.github/workflows/nightly-models.yml`, `chore(ops)`), docs (`docs(adr)`), planning (`docs(planning)`), each with its `git add` paths, then the push and `gh pr create --base main` commands.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.
