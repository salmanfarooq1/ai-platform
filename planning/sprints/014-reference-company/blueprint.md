# Sprint 014: Reference company. Blueprint

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

## 1. Personas
- Store six persona files under `data/reference-company/personas/`: producer, steward, consumer, operator, auditor and agent-developer.
- Each file lists only implemented scopes and names tenant-wide journey policy scenarios. Note that per-persona policy and column masking are not built.
- `scripts/showcase/setup_personas.sh` uses public identity admin functions with an explicit existing tenant slug and operator DSN. It never creates a tenant.
- Keep issued keys in memory with tracing off. Write `.showcase/keys.env` atomically, mode 0600 in a mode 0700 directory. Reject symlinks and foreign ownership. Bind the manifest to the tenant ID and slug; each persona stores only its key prefix and desired-scope hash.
- A rerun finds principals by name and reuses valid saved keys; otherwise it replaces the key and revokes only the issued prefix recorded in the manifest. Missing manifest state causes fresh issuance without revocation. Warn with the count and prefixes of other active keys left untouched. `--replace <persona>` forces rotation. The manifest binds runs to one tenant. No claim marker, freshness check or intent journal is required.
- Ignore `.showcase/` in git, Docker/build contexts and evidence artifacts. M0 retains full server stderr there in an exclusively created `m0-server.log` with mode 0600; stdout contains fixed reasons and exception class names only.

## 2. M0 showcase
- `scripts/showcase/m0.sh` uses `set -euo pipefail`. Each step prints `PASS`, `FAIL` or `SKIP` and a short reason.
- Read the policy head, then publish a journey baseline with `expected_version=head` (0 when absent), and the deny with `expected_version=baseline_version`. A conflict rolls back the caller transaction.
- Set a journey baseline policy as a new version. Then omit the resolved local chat model from policy and run consumer search. It must be denied and the Ollama request count must not change. This zero-inference proof uses Sprint 013's request-level admission check.
- The auditor finds decisions through `GET /v1/decisions?request_id=...`, then fetches and verifies the deny receipt offline, including signature and model identity from the Sprint 013 catalog.
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
