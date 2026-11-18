# Sprint 015: Acceptance

Run `bash planning/sprints/015-local-poc-lifecycle/accept.sh` from the prepared
worktree. Paths below are relative to this pack. Every item needs captured command
output; a builder's prose is not evidence. Leave boxes open until independently run.

- [ ] **A0. Product gaps closed (WP0).** Baseline allows models, explicit journey
  deny excludes only its alias and is restored safely; Poetry resolves from the
  environment; missing caller/context fails closed. Tests: WP0 in `test-spec.md`.
  Evidence: `evidence/accept-unit.log`, `accept-new-live.log`, `accept-playwright.log`.
- [ ] **A1. Default stack and release (WP1).** One up initializes four healthy
  default services; API and worker share the hardened image. All external images
  and bases have verified index pins; local output identity is recorded honestly.
  Tests: WP1. Evidence: `evidence/accept-new-live.log`, `accept-unit.log`,
  `accept-pins.log`, `accept-image-scan.log`.
- [ ] **A2. Persistent key (WP2).** Private key survives down/up outside volumes,
  API and worker share it, backups carry public identity only; mismatched restore
  requires the trusted previous public key. Tests: WP2. Evidence:
  `evidence/accept-unit.log`, `accept-new-live.log`, `accept-live-m0.log`.
- [ ] **A3. Online backup (WP3).** Purge lock, in-container dump, restic command
  failure propagation, object completeness and dump-derived manifest pass. API
  remains governed. Valkey losses are reported and queued work recovers from
  Postgres; same-day cost counters are restored before health. Down checks live
  counts and chain heads against the manifest. Tests: WP3 backup/loss
  rows. Evidence: `evidence/accept-new-live.log`, `accept-unit.log`.
- [ ] **A4. Checked teardown and restore (WP3).** Marker/ref/live-state/age/read-data/scratch
  gates pass in order; each negative refuses destruction. Fresh restore verifies
  every binding before healthy. Tests: WP3 down/restore rows. Evidence:
  `evidence/accept-new-live.log`, `accept-unit.log`, `accept-live-m0.log`.
- [ ] **A5. M0 closes (WP4).** Real shell journey runs backup/down/up on explicitly
  owned fixture data, compares counts/heads, rechecks saved receipts offline and
  records a new governed call; the fixture stack is fully torn down. No required
  SKIP. Browser journey also passes.
  Tests: WP4 and `m0 journey`. Evidence: `evidence/accept-live-m0.log`,
  `accept-playwright.log`, `accept-new-live.log`. Owner tags `v0.15.0` afterward.
- [ ] **A-sec.** Every exact threat-model node is collected and passes in the unit
  or new-live log. No secret material in snapshots, logs or evidence. Independent
  Sol/Terra cross-review per launch has no unresolved finding.
- [ ] **A-mem.** Capture actual `docker stats --no-stream` for API, worker and
  on-demand restic in `evidence/accept-new-live.log`; no invented memory figures.
- [ ] **A-checks.** All runner checks pass: lint, types, import/port contracts,
  unit, full live tiers, new live tests, exact skip guard, UI checks, showcase
  Playwright, eval, docs, pins and final image scans. Evidence: `evidence/checks.txt`
  and each `accept-*.log`, `all.xml`, `unit.xml`, `new-live.xml`. New tests have zero
  skips; baseline counts in `evidence/baseline/` give the final delta. MAP,
  CHANGELOG, operator docs and report are updated before closure.
