# Sprint 045: Packaging and editions. Requirements

Packaging, all modules. No new feature, no UI change beyond the modules list.

## Scope
1. Per-module Python packages.
   - One wheel per module: kernel, gateway (with the evidence core), evidence (M2), agents (M3), data plane (M4), lineage (M5), insights (M6).
   - Each module registers itself through the entry point group `platform.modules`. The module registry from Sprint 013 discovers them.
   - A wheel holds only its own packages. Inter-wheel versions are pinned exactly.
2. Edition installs.
   - Gateway, Assurance, Agents, Data and Full, each as a wheel set, an `ENABLED_MODULES` value and a compose file or profile set.
   - Each edition installs from wheels on a clean machine, with no repo source on the path.
3. Release SBOM and licence report.
   - CycloneDX for the wheels, the npm build, the images and the models from `models.lock`, merged into one release SBOM.
   - A licence report for the whole stack; the gate fails on any non-OSI licence in the default stack.
4. Runbooks.
   - Upgrade: DuckDB and DuckLake catalog upgrades, a Postgres major upgrade, image and model digest bumps.
   - Backup and restore: Postgres (platform and lakehouse catalog), object store, keys and the transparency log. Tested on a copy.
5. Release gate.
   - The edition smoke matrix, run from wheels, becomes a required gate for a release tag, with the SBOM and licence report.

## Out of scope
- Publishing wheels or images to a public index or registry.
- Helm charts, Kubernetes or hosted installs (program 3).
- The showcase scripts (Sprint 046).

## Nav placement
No new page. Platform > Modules shows the installed version of each module.

## Questions this sprint closes
- None.
