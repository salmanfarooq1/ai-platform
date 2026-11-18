# Sprint 015: Architect readiness

Pack drafted; implementation and acceptance have not run. Test names are a build
contract, not claims that those tests already exist or pass.

## Verified source facts
- Compose has Postgres, Valkey and worker by default; API is absent. Worker has
  no read-only/capability/no-new-privileges hardening. WP1 fixes both services.
- Dockerfile has digest-pinned bases and build-time Poetry. The old wheelhouse
  premise is false; preserve the current build method.
- `evidence/receipts.py` derives key id from SHA-256 of public bytes. Settings
  accepts an inline private key and comma-separated previous public keys, no file
  setting. API and purge worker must share the file-backed key in WP2.
- Local objects are immutable SHA-256 files written by atomic rename. Purge has
  no backup advisory lock. Jobs and outbox are in Postgres; no Valkey job queue.
- Reference-company seed changes `allowed_models` to `[]`; M0's
  `publish_journey_policy` already excludes only the selected alias. WP0 aligns
  the browser setup with that seam and preserves versioned restoration.
- Both showcase server commands hardcode Poetry. Legacy citation generation
  permits direct LLM calls without governance. Both are WP0 product fixes.
- `m0.sh` delegates to `m0.py`; the latter contains the missing-drill SKIP.
- Existing pin checker validates digest syntax, not index media type. Local app
  builds have image IDs; they must not be misrepresented as external index pins.

## Before an implementation launch
- Owner gave the sprint go-ahead on 2026-11-17. The Architect launches the WPs
  using the cross-model route in builder-brief.
- Capture `accept.sh --baseline` with existing tools. Keep the full report and
  test counts; no baseline measurements are claimed by this drafting pass.
- Verify the exact restic 0.19.x index, the one staged backup and final artifact
  scans. Never invent a pin.
- Check actual ports and existing resources. Per-stack projects and labelled
  marker-owned volumes protect the developer project. The backup age defaults
  to 86400 seconds. Confirm the drill target is fixture-owned and fully torn down.
- Check R1–R5 against the edited pack before launch; record the second look in
  `pre-start-review.md`.
- Cross-model review checks every threat node against test-spec and independently
  runs package checks. Final acceptance requires the real shell and browser runs.

Planning changes do not establish implementation readiness of the laptop. There
are no fabricated baseline, image-index, memory, drill or release measurements.
