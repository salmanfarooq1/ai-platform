# Sprint 011: Architect review

**Current verdict: Sprint 011 accepted for local successor implementation. Required remote CI remains pending human landing.**

## Corrective re-review

The Architect independently reran the changed CI, inventory, pinning, licence and MCP suites: **59 passed, no skips**. Captured results: [output](evidence/architect-recheck-controls.txt), [JUnit](evidence/architect-recheck-controls.xml). Source inspection and those regressions close H1 and M1–M3 below. MCP 2.2 now exposes controlled expected denial reasons and masks unexpected failures, including sentinel-secret cases.

The final licence and image gates remain mandatory. The selected bounded UI dependency migration, exact-artifact NumPy audit, compatible image replacements and permission to begin part b are recorded in [architect-disposition.md](architect-disposition.md). This supersedes the work-order restriction in the original review, without signing off A4, A6 or the sprint. Current reports and final-stack evidence determine their disposition. No commit, push or merge was run.

## Autonomous continuation re-review

The expanded controls independently pass **84 tests**, including installed-artifact drift, exact `WITH` expressions, parsed optional-service builds and immutable scanner targets: [output](evidence/architect-autonomous-controls.txt), [JUnit](evidence/architect-autonomous-controls.xml). The Architect reran the NumPy source/compiler/member/symbol audit against the exact upstream wheel: [captured output](evidence/architect-numpy-audit.txt), [audit artifacts](evidence/architect-numpy-audit/). All guarded member hashes match the upstream inventory, excluding installer-managed RECORD. This supports the exact-artifact metadata correction under the documented limits; it is not a blanket determination for another build or platform.

**A4 now passes:** the full unchanged OSI gate [returns zero](evidence/architect-real-licence.txt), and the seeded non-OSI fixture [is rejected](evidence/architect-non-osi-fixture.txt). Original notices remain. Final-tree SBOMs, image pins/scans, browser and full-stack regression results remain open. Earlier passed A5/A7 snapshots must be refreshed after the selected dependency/build changes; no whole-sprint sign-off is claimed.

## Original review (historical findings)

The following describes the pre-correction tree and its captured evidence. Its pending statuses are historical; the corrective disposition above governs the current work.

Reviewed the working diff, new CI and supply-chain scripts, changed tests, sprint contract and builder evidence. This is a review of the current part-a implementation. Part b has not started. Product files were preserved during the review.

## Findings

### H1: UI dependency changes skip their supply-chain gate

Location: [workflow condition](../../../.github/workflows/tests.yml#L159), [change classifier](../../../scripts/ci/change_scope.py#L14).

A change confined to `ui/package.json` and `ui/package-lock.json` produces `backend=false, frontend=true`. The supply-chain job requires `backend=true`, so the npm licence check and npm SBOM never run on that dependency change. No equivalent gate exists in the frontend workflow. This defeats the new dependency control on a common update path.

**Required:** run the supply-chain gate for frontend dependency changes as well as backend changes. Keep explicit required-check results. Add a test that combines the classifier output with the actual job condition; a classifier-only assertion misses the defect.

### M1: The npm inventory validator accepts missing dependencies

Location: [npm validation](../../../scripts/supply_chain/licence_metadata.py#L105).

Both `{}` and an inventory containing only one fabricated MIT package exit successfully, while the UI declares 19 direct production dependencies. Unlike the Python path, the npm path never supplies a required inventory. Successful validation therefore proves only that the supplied rows have allowed licences. It does not establish coverage of the installed production tree. The probe does not claim that the current npm collector actually omitted packages.

**Required:** independently enumerate installed production dependencies and reconcile exact package/version identities with licence metadata. Reject empty, incomplete and unexpected inventories; account explicitly for platform-specific optional packages and the private first-party root. Test the CLI as well as expression parsing.

### M2: Digest-shaped comments satisfy the image-pin checker

Location: [digest check](../../../scripts/supply_chain/check_pins.py#L14).

The valid YAML value `image: example/probe:latest # @sha256:<64 hex digits>` passes. The parsed image has no digest: the checker searches the entire source line, including its comment. Current image references are pinned; this finding concerns the enforcement control.

**Required:** parse Compose and workflow image values, and validate the image token of each Dockerfile `FROM`. Check the complete reference, excluding comments. Cover quoted values, mutable tags with digest comments, malformed digests and valid digest references.

### M3: A licence failure suppresses independent evidence

Location: [supply-chain steps](../../../.github/workflows/tests.yml#L178).

The licence step precedes SBOM generation/upload and scanner installation/execution. None of those later steps has an independent failure condition, so the known licence failure prevents them from running. GitHub applies a default success condition to steps; see its [status-check documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions).

This does not make the workflow pass. It prevents a failing pull request from reporting its other supply-chain results and publishing the requested SBOMs.

**Required:** separate independent checks into jobs or execute all eligible checks and combine their exit statuses. Upload generated evidence after check failures. Preserve failure of the overall gate; do not use an unexamined `continue-on-error`. Prove that a seeded licence failure still permits image checking and SBOM upload, while the final result remains failed.

All four reproductions are in [architect-probes.py](evidence/architect-probes.py), with [captured output](evidence/architect-probes.txt). Preserve these as before-fix evidence; the assertions intentionally describe the defective tree.

## Verification

| Check | Review result | Evidence |
|---|---|---|
| Changed-area regression suite | 44 passed, no skips | [output](evidence/architect-focused.txt), [JUnit](evidence/architect-focused.xml) |
| Ruff | Pass | [static checks](evidence/architect-static.txt) |
| Mypy | Pass, 147 files | [static checks](evidence/architect-static.txt) |
| Product documentation links | Pass, 32 files | [static checks](evidence/architect-static.txt) |
| Current image references | Pin checker passes, subject to M2 | [static checks](evidence/architect-static.txt) |
| Lock and exports with Poetry 2.3.3 / export plugin 1.10.1 | Fresh lock; both exports match | [tooling check](evidence/architect-tooling.txt) |
| Real Python licence gate | Fails on the recorded NumPy expression | [fresh output](evidence/architect-licence.txt) |
| API snapshot and UI dependency files | Unchanged from the branch baseline | [scope check](evidence/architect-scope.txt) |

The ambient Poetry 2.2.1 reported a stale lock. Rechecking with the required 2.3.3 resolved that warning; it is not a repository defect. The first pytest attempt hit a sandbox socket restriction; the unchanged focused suite passed once the environment allowed its local socket.

The full backend, Vitest, Playwright and image runs were inspected from the builder's captured evidence, not repeated in this review. Their reported totals remain 1608 backend passes, 10 allowed live-MinIO skips, 207 Vitest passes and 82 Playwright passes. These totals do not close the failing supply-chain gates.

## Acceptance disposition

| Item | Disposition |
|---|---|
| A1 | Rework: control findings and existing gate failures remain |
| A2, A3 | Pass on focused re-run and source inspection |
| A4 | Blocked: NumPy, caniuse-lite and GSAP terms under the present policy; also fix H1 and M1 |
| A5 | Local generation supported by builder evidence; CI delivery needs M3 fixed |
| A6 | Blocked: four failed image scans and unfinished Ollama scan; also fix M3 |
| A7 | Partial: current digests and Poetry verified; MCP 2.2 missing and M2 open |
| A8 | Accept the scoped LiteLLM check |
| B1–B8, A-mem | Pending part-a gate |
| A-sec | Incomplete: add the control regressions above; part-b threats remain pending |

The LiteLLM incident account agrees with the project's [primary notice](https://docs.litellm.ai/blog/security-update-march-2026): the named affected releases are 1.82.7 and 1.82.8. The builder limits its lock-history conclusion appropriately. This is not a statement about unrecorded installations or other advisories.

## Architectural dispositions

- **Keep the present acceptance gates.** Part b and Sprint 012 remain gated. H1 and M1–M3 are part-a corrections within the existing infrastructure scope.
- **Select a narrow MCP compatibility amendment.** Keep the target 2.2.0 pin. The supported path is to translate expected gateway denials to the SDK's expected tool/resource errors at the MCP boundary, with a controlled reason code. Unexpected exceptions retain SDK masking. Preserve existing denial assertions and add a sentinel-secret failure case. The change began in the SDK's [2.1 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.1.0) and remains in the [2.2 error contract](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/src/mcp/server/mcpserver/exceptions.py). Record the bounded source-scope amendment in the pack before implementation; no transport redesign is needed.
- **Keep licence policy unchanged.** No CC0, CC-BY or GSAP exemption is approved here. NumPy is a conflict with the stated policy, not a finding that it is proprietary. Any metadata correction needs evidence for the exact distributed artifact and its bundled components. The UI dependency migration needs its own bounded pack amendment before source changes.
- **Require verified image remediation.** Propose compatible fixed pins or rebuilds with primary sources and digests. Keep Postgres on 16. Capture the full final scan including Ollama; a timeout or partial run stays incomplete.
- **Accept the implementation choices already justified:** hash exports without the unsupported `--with-hashes` flag; isolated test services; stricter digest and skip assertions; waiting for both MCP replies within the original deadline. These do not weaken tests.
- **Keep the prepared threat template in this sprint until the location conflict is amended in the pack.** Its contents are adequate; the conflicting requested destination remains a planning item.

The next pass is specified in [architect-handoff.md](architect-handoff.md). No product fix, commit, push or acceptance sign-off was performed by this review.

## Final artifact review in progress

The independently rerun final control suite passes **87 tests** (`evidence/architect-final-controls.txt`, `.xml`). SeaweedFS and Ollama immutable security artifacts pass the unchanged fixed-critical scan. Final Compose review caught the lake services still selecting the vulnerable upstream artifact; both services now build the reviewed recipe, with a six-service regression. Live signed PUT/GET, changed-key denial and actual expiry denial pass (`evidence/stack-seaweed-presign-negative.txt`). Consolidated images and final backend/browser tiers still gate acceptance. A shared-cache validation interference was isolated without altering product behavior or assertions; preserve its failed attempt alongside the final isolated results.

The actual common image path now returns **zero for all 12 immutable artifacts** (`evidence/architect-consolidated-images.txt`, `architect-consolidated-image-results.json`). The Architect preserved every image SBOM/identity and independently compared seven artifact pairs: rootfs layers, platform and runtime configuration exactly match the previously live-verified runtime/init/worker artifacts (`architect-artifact-runtime-binding.json`). Final Ruff and mypy pass (147 files). Only final full backend/browser results gate local successor acceptance; remote CI remains an explicitly pending human landing gate, never an asserted local run.


## Final Compose control review

The final shared Compose reader rejects unregistered root Compose files, top-level `include`, and service-level `extends` before any image/build-service mode can emit results. The 56-case supply-chain control suite passes, including 9 extra-filename and 6 indirection/mode regressions; Ruff and the standard, `--compose-images` and `--built-services` checks pass. Current root inventory contains only `docker-compose.yml`. Captured evidence is in `evidence/compose-indirection-*.txt` and `evidence/compose-final-inventory.txt`. This review does not sign off Sprint 011; final integration/browser evidence and remote CI remain pending.

## Final backend review

Final unit and full integration/e2e tiers pass: **884 + 835 = 1719 passed**, exactly **10 allowed skips**. The captured identity audit retains all 1591 observed baseline cases and accounts for 138 additions (`evidence/architect-final-counts.txt`, `architect-final-count-audit.py`). Source bindings match both isolated runners (`architect-final-runner-source-binding.json`). Failed attempts remain preserved. Browser acceptance is still open.

## Final local acceptance

The complete final browser tier passes **82 tests** (`evidence/architect-final-browser-green.txt`), including existing accessibility, responsive, reduced-motion and real console journeys. Together with 207 UI unit cases, final backend/static checks, exact skip reconciliation, unchanged licence policy and all 12 immutable image scans, this closes every local A/B acceptance item. Historical failures remain preserved. The recorded WSL clock issue was not “fixed” by changing assertions, deadlines or signed history; original runtime settings are restored. Basic chain integrity remains verified, while the existing wall-time ordering assumption is explicitly recorded for evidence-core review. No commit, push, merge or remote CI run is claimed.

The final snapshot review also closed a CI landing gap: newly captured metadata would be flagged after commit even though the pre-existing history scan was clean. All 189 findings were classified and bound to source-file hashes (`evidence/architect-secret-metadata-review.json`); none is a credential. Four narrow generic-rule metadata exceptions retain every default rule. The actual CLI guard passes positive metadata and rejects adjacent credentials, unknown values, wrong paths and a separate default credential type (`architect-secret-controls.txt`); CI runs it before the unchanged history scan. The 884-case unit tier and Ruff pass after this correction. The final prerequisite is snapshot v3; earlier inventory and failed raw scan remain preserved.
