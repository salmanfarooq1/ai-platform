# Sprint 014: Reference company. Blueprint

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

## 1. Personas
- Store six persona files under `data/reference-company/personas/`: producer, steward, consumer, operator, auditor and agent-developer.
- Each file lists only implemented scopes and names tenant-wide journey policy scenarios. Note that per-persona policy and column masking are not built.
- `scripts/showcase/setup_personas.sh` uses the identity admin CLI with an explicitly verified fixture-owned tenant. It never creates a tenant.
- Capture one-time key output privately with tracing off. Write `.showcase/keys.env` atomically, mode 0600 in a mode 0700 directory. Reject symlinks and foreign ownership. Keep a separate manifest with principal ids, key prefixes and a hash of desired scopes.
- A rerun validates and reuses existing keys. Missing, revoked or mismatched keys stop. `--replace <persona>` explicitly replaces one persona's key.
- Ignore `.showcase/` in git, Docker/build contexts and evidence artifacts.

## 2. M0 showcase
- `scripts/showcase/m0.sh` uses `set -euo pipefail`. Each step prints `PASS`, `FAIL` or `SKIP` and a short reason.
- Set a journey baseline policy as a new version. Then omit the resolved local chat model from policy and run consumer search. It must be denied and the Ollama request count must not change. This zero-inference proof uses Sprint 013's request-level admission check.
- The auditor fetches and verifies the deny receipt offline, including signature and model identity from the Sprint 013 catalog.
- Start an owned API process with `ENABLED_MODULES=gateway` on a free port. The Modules page shows agents off. The agent-developer credential gets the recorded `module_disabled` response; a scoped credential reads `/v1/system/modules`.
- Restore the baseline as a new policy version only if the current head is still the journey's own version. Never delete history or overwrite a concurrent change.
- The last step runs the Sprint 015 restore drill (`scripts/verify/poc-drill.sh`): `poc backup`, `poc down`, `poc up`, then it verifies the restored chain head and an old receipt. So one script proves every M0 step.
- `ui/e2e/showcase-m0.spec.ts` has its own Playwright project, seed and API server. It does not change policy beneath other browser workers.

## 3. Layout
```text
data/reference-company/personas/*.json
scripts/showcase/setup_personas.sh
scripts/showcase/m0.sh
ui/e2e/showcase-m0.spec.ts
```

## 4. Out of scope
Reference data assets belong to Sprint 021. Cloud lifecycle work belongs to Sprint 031 at the latest.
