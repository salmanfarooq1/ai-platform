# Sprint 015: Local POC lifecycle. Requirements

Infrastructure and packaging, Kernel. Depends on accepted 013 and 014. Closes M0;
the owner creates release tag `v0.15.0` after acceptance.

## Scope
1. **WP0: close product gaps first.** M0 step: explicit deny before inference.
   Seed the reference-company baseline with `allowed_models: "*"`. The browser
   journey explicitly excludes only its alias through `publish_journey_policy`,
   then restores policy with compare-and-swap, including failure cleanup.
   Resolve Poetry from the environment. Require a governed caller and context in
   citation generation and its routing wrapper; missing either fails closed.
2. **WP1: one-command stack and manifest.** M0 step: `scripts/poc up <stack>`.
   Default services are Postgres, Valkey, API and worker only (ADR-0035).
   API and worker share one app artifact and are hardened and healthchecked.
   Every external image and Dockerfile base is pinned by multi-arch index digest;
   verify media type, not just digest spelling. Record local app output identity
   separately and bind it to the release manifest; never call an image ID an index.
3. **WP2: persistent signing.** M0 step: signed receipts survive restart.
   Create `.poc/<stack>/receipt-signing.key` once, mode 0600, outside volumes,
   gitignored and excluded from build contexts. Mount as a read-only secret in
   API and worker. Data backup holds key id and public key only. Restore rejects
   another active key unless the exact old public key is configured in
   `receipt_previous_public_keys`. Document separate operator key backup.
4. **WP3: online recovery.** M0 step: `poc backup`, `down`, `up` restores.
   Hold the purge advisory lock; dump inside Postgres; copy immutable objects;
   verify every reference from the dump. Bind schema, dump, objects, row counts,
   tenant chain heads, public signing identity and release manifest in one manifest.
   Stage the dump, objects and manifest for one tagged restic snapshot. Use official
   restic 0.19.x, index pinned, with a local repository and 0600 password file.
   Record daily tenant cost counters; restore them on the same UTC day before health.
   Report Valkey losses and prove queued jobs survive in Postgres. Stop writers for
   `down`; check marker, latest reference, live counts and heads, age, then restic
   read-data and scratch restore. Age defaults to 86400 seconds and can be overridden.
   Restart services on refusal. Use isolated per-stack Compose projects and protect
   developer volumes by marker and project label.
5. **WP4: real M0 recovery drill.** M0 step: the full journey closes.
   Replace the drill placeholder in the `m0.sh` entry path. Compare restored row
   counts and chain heads before new traffic, verify saved receipts offline,
   then execute a new governed call. Every required step fails if unavailable.

## Boundaries
Online capture keeps API, workers and relay operating; governed calls remain
recorded. No maintenance mode or audit exception. Optional services stay off on
`up`; `backup` starts restic on demand. Remote storage and maintenance are deferred
to the cloud track. No rclone, wheelhouse rebuild, paid provider call or publication.

## UI and public seams
No new page. Restore the existing Ask → Decisions → Receipt → Modules browser
journey. Rule 10 applies: no showcase-only shortcuts; add general product support
with tests for every missing operator seam. Showcase code uses API, CLI or public
admin functions, never product-table SQL or private imports.

## Resolved inputs
See `planning/QUESTIONS.md` for the backup-age default and per-stack ownership.
