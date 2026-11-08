# Sprint 011: Corrective builder handoff

Work on the existing `sprint/011-baseline-and-stack` branch. Read [qa-review.md](qa-review.md), then the existing sprint contract. Preserve unrelated files, the previous evidence and the existing tests. Part b retains its part-a-green gate.

## First pass: controls within the current scope

1. **H1: CI coverage.** Run the npm licence and SBOM controls on UI dependency changes. A shared supply-chain job may use both scope outputs, or expose a separate supply-chain output. Test the workflow condition together with its classifier, including UI lock-only changes, backend changes and documentation-only changes. A failed or missing scope result must not become a passing substitute for a required control.
2. **M1: npm inventory.** Build an independent inventory of the installed production closure. Reconcile package names and exact versions, with explicit handling of optional platform packages and the private root. Add CLI regressions for empty, partial, version-mismatched and complete metadata. Keep the existing non-OSI and exact-version exception tests.
3. **M2: image references.** Validate parsed image references instead of source lines. Handle Compose values, workflow service images and Dockerfile base-image tokens. Add positive and negative fixtures, including the comment reproduction in the review.
4. **M3: independent results.** Run licence, SBOM and image controls independently after successful prerequisite installation. Publish the generated artifacts despite a sibling control failure, and make the aggregate result fail if any required control fails. Add a bounded stubbed execution test that seeds a licence failure, observes the other checks execute, and verifies the final nonzero result. A workflow-only assertion is insufficient proof of execution behavior.

Capture the new tests failing against the pre-fix implementation in a scratch copy and passing with the fixes. Add new evidence filenames; retain the original review probes as before-fix evidence.

## Pack amendments and remaining blockers

- **MCP amendment selected by the Architect:** permit only the expected-error compatibility work required for the 2.2.0 upgrade in `api/mcp/`. Add that bounded exception to the requirements, blueprint and brief before editing source. Route shapes, schemas, denial reasons and gateway enforcement stay the same. Translate only known `GatewayDenied` results to the SDK's expected error types, using controlled reason codes. Keep masking for unexpected exceptions; test that a sentinel secret in an unexpected exception reaches neither the response nor application logs. Run the original policy-denial and concurrent-reply cases unchanged, then the full integration tier with 2.2.0. Save fresh exports and pins.
- **Licences:** the OSI-only policy remains binding. Establish the exact dependency/artifact paths before proposing replacements or metadata corrections. NumPy's installed Highway notice names a CC0 component; the main BSD licence alone does not justify removing that term. Submit a concrete compliant artifact strategy or identify the remaining owner policy choice. For the UI, prepare a bounded dependency migration that preserves fonts, interactions, reduced-motion behavior and bundle boundaries. Put the source-scope amendment in the pack before changing UI code. A licence exception cannot replace that work.
- **Images:** propose verified compatible fixed image pins or reproducible rebuilds. Follow the security-fix exception for publication age and record sources, digests and the reason. Keep Postgres 16 and the existing volume data. Scan every final image, including Ollama, with a completed wrapper status. Redpanda's planned replacement does not by itself satisfy part-a acceptance.
- **Template location:** reconcile the requested `_template` destination with the recorded folder restriction in the pack. The prepared `threat-model-template.md` is ready to reuse. Avoid changing another sprint folder while that restriction applies.

These amendments preserve the gates. Licence-policy changes, unresolved scope conflicts, missing secrets, destructive operations and costs retain the stop conditions in `AGENTS.md`; continue the independent authorized items.

## Evidence and exit

- Run the updated control suite, ruff, mypy, the DDL guard, documentation checks, lock/export checks and the existing exact skip guard.
- Run the full backend tiers after dependency or MCP changes, with no new skips. Run the required UI checks after any approved UI dependency migration. State test deltas against the observed branch baseline.
- Keep independent licence, SBOM, secret-scan and image-scan results, including failed results. Retain hashes and exact versions in the evidence.
- Update the acceptance table, builder report, build log, STATE and CHANGELOG honestly. Request re-review after these corrections; part a passes only when every part-a gate actually passes.
- Add the corrective paths to the proposed commit blocks. Humans run all commit, push and merge commands.
