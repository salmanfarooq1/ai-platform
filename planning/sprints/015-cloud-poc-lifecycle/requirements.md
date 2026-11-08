# Sprint 015: Local POC lifecycle. Requirements

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Platform pillar, infra and packaging, Kernel. This sprint brings up, backs up and restores the local stack.

Depends on: Sprint 012. Runs in parallel with Sprint 013. Migration ids are assigned at launch.

## Scope
1. **Local release inputs.** Keep a release manifest with images pinned by digest in `scripts/release/build_manifest.py`. Keep the wheelhouse install in the app image.
2. **Local POC commands.** `scripts/poc` provides `up`, `backup`, `down` and `status` against the local host only. A `Runner` wraps `docker compose`, `restic` and `rclone` to a local folder. No OpenTofu and no SSH.
3. **Maintenance and backup.** Maintenance blocks non-health requests during capture. Workers and relays pause. Backup captures a consistent set and restore keeps the signing key. Turning maintenance on and off is a recorded decision.
4. **Restore drill.** Provide a drill script for the Architect to run on this machine. Its captured run output is the evidence. Do not use a placeholder or a "not run" evidence line.

## Out of scope
- OpenTofu interface and modules, cloud VM, Caddy TLS edge, remote `deploy/compose`, SSH handling, `poc-drill.yml`, `upgrade.yml` and upgrade-from-previous-release job. These belong to the cloud track in Sprint 031 at the latest.
- Any cloud provider, cloud spend or published image.

## Accepted exception
During maintenance capture, non-health requests receive 503 before `enforce()` and create no decision row because the database is being captured; turning maintenance on and off is recorded as a decision.

## Questions this sprint closes
- None.
