# Sprint 011 build log

## Architect review plan
1. Compare the working diff and new supply-chain scripts with the sprint contract.
2. Re-run focused regression checks and reproduce any control gaps in isolated fixtures.
3. Check the builder's evidence, dependency blockers and stated deviations.
4. Record findings, acceptance status and builder dispositions in `qa-review.md`; preserve product files and existing evidence.

## Baseline, before source changes
- Branch: `sprint/011-baseline-and-stack`, from `planning/sprint-plans`.
- Preserved the existing builder-brief edit and unrelated untracked files.
- Expected baseline: 1568 backend passed, 10 live-MinIO skips; 207 Vitest; 82 Playwright.
- Observed pytest: 878 passed, 3 failed, 710 skipped. Evidence: [baseline-pytest.txt](evidence/baseline-pytest.txt), [XML](evidence/baseline-pytest.xml).
- Observed Vitest: 207 passed. Evidence: [baseline-vitest.txt](evidence/baseline-vitest.txt).
- Playwright: 82 collected; execution requires unavailable Postgres and Redis. Evidence: [collection](evidence/baseline-playwright-list.txt), [run](evidence/baseline-playwright.txt).
- Installed locked UI dependencies and used a checksum-verified temporary Node 22 runtime. Did not install browsers.
- Linux Docker is absent; PATH resolves to an unusable Windows stub. Noninteractive sudo requires an unavailable password. Container checks are blocked, not passed.

## Part a plan
1. Add regression tests and capture failures for environment precedence, ignored docs, skips and licence fixtures.
2. Fix planning drift and the two bugs; implement the skip allowlist.
3. Verify pins from registries and primary release sources, preserve LiteLLM, and resolve with Poetry 2.3.3.
4. Build hash exports, licence gates, SBOM and package inspection; check LiteLLM against primary advisories.
5. Consolidate CI setup and supply-chain checks; update docs and templates within the allowed scope.
6. Run all available checks and record blockers honestly. Part b starts only after part a is green.

## Part a results so far
- Regression runs failed before the fixes (bugs-red, skips-red, supply-chain-red evidence). The mode, ignored-doc and skip tests now pass.
- The skip guard keeps the legacy CLI assertions. `--expect` must agree with the allowlist and cannot override it. An empty custom allowlist requires zero skips.
- Automatic review initially rejected a batch test edit and a shared-planning batch. Preserved exact-count assertions and demonstrated that the contract explicitly authorizes the historical-file move; the narrower actions passed review.
- Moved the historical commit plan without changing its contents. Corrected STATE and program links. Kept other sprint folders untouched.
- Locked MCP 2.2.0 and its mcp-types dependency with Poetry 2.3.3. LiteLLM remains 1.103.2. Exports contain hashes for 131 main and 166 main-plus-dev requirements.
- SBOMs validate as CycloneDX 1.6: 225 Python and 668 npm components. Python SBOM covers the installed environment, including optional tools already present.
- Reviewed odd Python licence labels against installed release licence files. NumPy's CC0 term blocks the real gate under the strict contract. Did not widen the allowlist.
- Added checksum-verified scanner installation and CI gates. GitHub release downloads and the Linux container runtime remain unavailable locally.
- The blueprint's other-sprint template conflicts with the direct scope rule; logged it and left the folder untouched.
- Part b has not started: the part-a green gate is not satisfied.

## Verification resumed
- Consulted the public 120x workflow once: implement the Architect's written contract, collect acceptance evidence, and leave review and commits to the owner.
- Docker is reachable. Created only the sprint's isolated Postgres/Redis containers on 15432/16379; unrelated services on 5432/8000 remain untouched.
- Strengthened the observability image test to require a version plus a 64-digit SHA-256 digest. Its previous tag-only expectation was stale after the intended pin change.
- Reviewed six full-history gitleaks findings: three public prefixes, an alg=none JWT rejection fixture, and two numeric chunk-size comments. Added exact fingerprints with reasons, retaining the earlier two exclusions. The full-history rerun is clean.
- CI installs only main plus requested groups, excluding optional training and lab dependencies. The temporary matching-browser image uses Python 3.11; no browser-install command was run.
- Fixed the missing executable bit on the required database setup script. It targets the isolated sprint database.
- Excluded generated test state and scratch tools from Docker build context.
- The original scope still forbids other sprint folders. NumPy's licence-policy conflict remains unresolved, so part b has not started.

## Verified blockers and security fixes
- MCP 2.2.0 failed the existing MCP policy-denial integration contract. Preserved the test, froze the working 2.0.0 baseline, and logged the required Architect compatibility decision. No MCP product code or route changed.
- Prevented pytest tracebacks from printing credential-bearing fixture arguments by selecting short tracebacks. Redacted the candidate-run fixture representations in captured evidence; assertions and test execution remain unchanged.
- The initial image scan identified critical fixes for Python, AnyIO and Debian packages. Verified primary advisories and fixed versions. Selected Python 3.11.17 by digest; direct inspection confirms fixed OpenSSL and Perl packages already in that image. Pinned AnyIO 4.14.2. LiteLLM is unchanged. No advisory was ignored.
- Production npm metadata adds two actual policy blockers: CC-BY-4.0 in caniuse-lite and GSAP's custom terms. Reviewed Geist's OFL-1.1 and webgl-constants' MIT text; the shared exception file binds these corrections to exact versions. Added three regression cases proving exceptions cannot approve non-OSI terms or another version.
- Prepared the threat-model template inside Sprint 011 for review. Did not write into the forbidden `_template` sprint folder.
- Automatic review rejected mounting the original workspace read/write into the browser image. The accepted alternative mounts only a selected-source scratch copy read/write and dependency directories read-only; dotenv files and unrelated root files are excluded.
- Browser tests use the verified official image with its matching preinstalled browser. No browser installation command ran. Duplicate image dependency downloads timed out; reusing the verified installed test environment resolved setup.

## Integration verification
- All 82 browser cases passed in the isolated matching-browser runtime. All 777 unit cases passed after the final dependency changes. The named part-a control suite passes 41 cases.
- The full integration tier found a reply-order race in the existing MCP scope test. The test waited only for reply 3 before reading reply 2, while the SDK dispatches tools concurrently. Required both replies within the unchanged five-second bound and preserved every scope/content assertion. The focused rerun passes; the full tier will be rerun.
- The OCI application image builds with the verified security pins. Added a persistent Poetry build cache and seeded it only with cached wheels whose hashes match the current main lock, after repeated registry read timeouts. No dependency hash check was bypassed.

## Final supply-chain verification
- Regenerated both SBOMs and independently validated each against the installed strict CycloneDX schema: 225 Python and 668 npm components, both spec 1.6.
- The rebuilt application passes the fixable-critical image gate. Grafana 13.2.2 fails it with critical OpenSSL and Go findings. The remaining image scans continue independently; no advisory ignore is added. A6 cannot be signed off.
- Marked only A2, A3, A5 and A8 as evidenced passes. All part-b checks remain unchecked under the mandatory part-a gate.
- Added a bounded timeout to image pulls and scans so an unavailable registry cannot prevent checks of the other images. A timeout is a gate failure, never an advisory acceptance.
- The complete integration/e2e rerun passes: 831 passed, 10 original MinIO skips, 777 unit cases deselected. Together with the final unit run: 1608 passed and 10 skips, 27 added cases against actual pre-change collection. The exact skip guard passes. Vitest remains 207 and Playwright 82 passed.
- Changing the scan script while its shell was still reading it disrupted the final shell status line. Archived that complete set of individual image outputs as `image-scan-before-timeout.txt` and reran the unchanged final script over cached images. The old run is not used as completed gate evidence.
- The first Ollama client exceeded the bounded wait; its large layer finished downloading at that boundary. A separate retry pulled the exact pinned digest successfully. Both results are retained.

## Handoff status
- The session transition interrupted the corrected full image run and Ollama scan. No scanner process remains. Preserved all attempts; `image-scan-summary.txt` extracts their actual statuses. No full image-gate pass is claimed.
- Completed individual scans: application and Redis pass; Grafana, pgvector, Prometheus and Redpanda reject fixable critical findings. Ollama is pulled by digest but its scan is unverified. Stop the image item under the documented advisory rule; no exemption is invented.
- All unaffected part-a implementation and runtime verification is finished. A4, A6 and A7 remain blocked; therefore A1 and the mandatory part-a gate cannot pass. Part b, its threat checks and its memory measurements remain unstarted. The sprint is not complete.
- Report, acceptance status, STATE and CHANGELOG are updated. Proposed commits are text only. Architect decisions are required before the remaining contract can be fulfilled.

## Architect review result
- Verdict: rework. Reproduced one high and three medium control findings: UI dependency changes bypass supply-chain CI; npm metadata accepts incomplete inventories; digest comments satisfy the pin checker; a licence failure suppresses independent SBOM and image results.
- The focused suite passes 44 cases. Ruff and mypy pass. Poetry 2.3.3 verifies the lock and reproduces both hash exports unchanged; the ambient 2.2.1 warning was a tooling mismatch.
- Saved captured review output, reproducible probes, `qa-review.md` and `architect-handoff.md`. The real Python licence check still rejects the recorded NumPy term.
- Selected the supported expected-error migration path for MCP, subject to recording the bounded pack amendment before source work. No licence-policy waiver, part-b gate change or acceptance sign-off.
- Product files and previous evidence are preserved. No commit or push ran.

## Corrective pass plan
1. Preserve the review probes; add control regressions and capture their failures in a scratch copy.
2. Fix workflow coverage, exact npm inventory reconciliation, parsed image references and independent check aggregation.
3. Record the selected MCP amendment, restore 2.2.0 and verify controlled denials plus unexpected-error masking.
4. Run focused and full required checks, keep licence/image results independent, and update the blocked acceptance report. Part b remains gated.
- Corrective control regressions fail in the preserved scratch tree (20 failures, 13 passes) and all 57 focused cases pass after the fixes. M3 runs a seeded failed licence check followed by SBOM and image checks, verifies nonzero aggregate status, and evaluates the real artifact-upload condition after that failure.
- Independent npm inventory contains 264 installed production identities and explicitly excludes 27 absent optional packages and the private root. The pinned collector omitted two installed optional artifacts; per-artifact collection closes those gaps. The reconciled real inventory rejects the original caniuse-lite and GSAP licences.
- Restored MCP 2.2.0 and mcp-types 2.2.0; no other dependency changes. SDK registration wraps only the boundary: catalogued gateway reasons become expected errors; unexpected errors remain unexpected and carry sanitized causes. Removed raw provider-exception logging from MCP handlers. The original three policy/concurrent-reply cases pass unchanged.
- The new expected-error unit assertion initially omitted the SDK's documented tool-name prefix. Corrected that new expectation to the exact prefixed message; the existing denial assertions were preserved. Sentinel response/log cases pass for tools, resources and an actual registered provider failure.
- The live runner exposed multiline non-FROM Dockerfile instructions to the new tokenizer. Limited shell-token parsing to FROM instructions and expanded the positive Dockerfile fixture. Current parsed-reference checks pass. Its earlier live attempt is retained as a failure, not silently relabelled.
- Reviewed and hash-verified both exact MCP 2.2 wheels before moving their non-SPDX classifier corrections from 2.0 to 2.2. The real Python gate again fails only on the existing NumPy term.
- The standalone SBOM validation finished before an attempted duplicate-process cancellation; no process was killed. The independent runner continues its own full validation. No test or required check is skipped.
- Verified and scanned Grafana 13.2.4 by registry digest as a compatible security candidate. It still rejects GO-2026-6612 in embedded components, so compose remains unchanged and no finding is accepted. The compatible rebuild requirements and primary sources are in `image-remediation.md`.

## Completion discipline
- Saved the owner's instruction in CODEX.md: finish authorized work, checks and documentation before ending the turn; keep long-running verification in the active turn. Do not use status-only final replies.
- Verified the prior integration/image jobs no longer exist and their outputs are incomplete. Preserve them as interrupted attempts and rerun unfinished checks; never report their partial progress as a pass.
- The resumed full tier found the sprint stores exited after the prior ended turn. Its captured run had 710 service skips and was rejected by the exact skip guard; it is preserved as `rework-int-e2e-unavailable.*`. Restarted only the isolated stores, verified host ports and in-container health, and reran the full tier. No skip was approved or added.
- Added two adversarial exact-name cases: npm names differing by underscore/dot must not borrow a hyphenated package's reviewed exception. Both failed before the fix. Preserve exact npm names while retaining PEP 503 normalization only for Python distributions. This is part of M1 exact-identity enforcement.
- Final expanded focused suite: 59 passed. Final complete unit tier: 817 passed, no skips. Corrective delta is 40 cases (33 control, 5 MCP, 2 exact npm exception-name cases), on top of the earlier 27 part-a additions.
- Fresh image data identifies critical GHSA-6q48-6c7w-9gw2 in certifi 2026.6.17. Verified the maintainer advisory and exact 2026.10.19 wheel hash, publication and MPL-2.0 licence before selecting the security-age exception. Resolving that pin without changing LiteLLM; current runtime jobs finish before the environment is updated.
- The independent real runner completed: exports 0, pins 0, licence 1, SBOM 0, scanner installer 7 (connectivity), images 1, aggregate 1. All final compose images were attempted; the host Ollama catalogue timed out at 900 seconds. Its same-input Docker-local retry is still running. Independent evidence and uploaded-artifact eligibility are not suppressed by the real licence failure.
- The rebuilt application passes the unchanged fixed-critical threshold after the Certifi-only pin. Ollama completed with scanner exit 2: fixed-critical Go x/net, x/crypto and stdlib findings; raw Docker-local output and exit are preserved. The full wrapper also completed with failure, rather than an interrupted status.
- The first complete MCP 2.2 tier finished: 829 passed, 10 original skips, 2 failures. The rate-limit test crossed its minute bucket and accepted the eleventh attempt (200); its expectation is valid only within one window. Freeze only the route module clock in that test, preserving every request and assertion; no route implementation changes. The worker process missed its existing health deadline under host/daemon latency; preserve that test unchanged and run the final tier beside the isolated stores.
- The first container-local probe correctly failed the existing loopback-only DNS guard for service names. Preserve it as failed evidence; do not relax the guard. A scratch-only runner provides loopback proxies to just the isolated Postgres/Redis services, with no host-published port. The deterministic sign-in case passes through this path; worker verification continues unchanged.
- Both runtime probes now pass (35.20 seconds total), including the unmodified worker deadline and graceful shutdown checks. Started the full final tier on the same loopback-only path. Final host unit tier passes all 817 cases after the Certifi update. Ruff and mypy pass.
- The new Certifi wheel reports a non-SPDX MPL classifier, so the old exact-version metadata correction correctly failed closed. Moved only that verified MPL-2.0 correction to 2026.10.19 using its hash-verified licence evidence. The real Python gate again rejects NumPy only; no non-OSI policy term was permitted. The sandbox SBOM retry failed registry DNS; preserved that output and reran with authorized network access.
- Final full integration/e2e tier passes: 831 passed, 10 original live-MinIO skips; exact skip guard returns 0. The unchanged worker test finishes in 9.99 seconds. All long-running verification results are collected before ending the turn.
- Final backend count is 1648 passed (817 unit + 831 integration/e2e), 10 skips, 1658 collected. The identity audit confirms all 1591 observed baseline cases remain and 67 were added (27 initial + 40 corrective). The first raw comparison flagged two random UUID parameter IDs; verified uuid4() at test_console_api.py:19 and normalized only those two identities in the audit. No test was changed for this comparison.
- Fresh focused recheck passes 50 control/licence/MCP cases; the earlier full focused run passed 59, including nine CI environment cases also covered by the final complete unit tier. Fresh SBOMs validate strictly: 225 Python, 668 npm, CycloneDX 1.6; recorded hashes include current Certifi. Lock/export, lint, mypy and DDL checks pass.
- Corrective implementation and unaffected verification are complete. Sprint 011 remains blocked by the three recorded dependency licence terms and five upstream images with fixed-critical findings; no policy waiver, unverified digest or part-b gate bypass was made. Final report, acceptance status, STATE, CHANGELOG and open questions are updated; proposed commits remain text only.
- Final generated documentation and link checks return 0 (32 files, no problems); report evidence links all exist. Source/scope audit confirms no other sprint folder, UI, migration or HTTP/OpenAPI change; the OpenAPI SHA remains unchanged. git diff --check is clean. The owner completion preference is saved in both AGENTS.md and CODEX.md for future repository sessions.

## Continued image remediation
- On the owner's continuation, refreshed primary registry metadata. Grafana 13.2.4 and pgvector 0.8.7-pg16 digests remain unchanged. Newly published Prometheus 3.15.1 and rebuilt Ollama 0.40.7 artifacts are candidates only; verify maintainer release notes, licences, scan results and compatibility before changing pins. Do not bypass licence policy or start part b.
- Accepted Prometheus 3.15.1 at its verified registry digest after a completed clean scan, exact artifact Apache licence inspection, existing-config validation and isolated old-WAL replay/query. Only its compose image reference changes; profiles, ports and volumes stay intact. The initial probe assumed a self-scrape within three seconds and failed before samples existed; preserve it and use bounded polling for actual samples. No existing test or data was weakened or deleted. Record the exact image publication and security-age exception; the project release page is unavailable, so do not invent its date.
- The tagged maintainer changelog became available through the primary raw-source endpoint and confirms Prometheus 3.15.1 release 2026-10-21, Go 1.27.3 and x/net 0.60.0 security fixes. Captured it without inferring dates. All 36 existing profile/control cases, parsed pin validation and observability Compose validation pass after the single pin change.
- Refreshed image status: application, Redis and Prometheus pass; Grafana, Ollama, pgvector and Redpanda remain blocked. Grafana/pgvector registry digests are unchanged. Captured latest Ollama source still declares the affected module versions; no newer tag is presumed fixed. No further source, dependency, UI, route, migration or other sprint change was made.
- Continued pass finalized: maintainer release/date and exact image licence are verified, Prometheus security/compatibility/profile checks pass, report and acceptance now show four remaining image blockers, and documentation checks pass again (32 files, no problems). All image scan and runtime jobs have completed; no part-b work or commit/push ran.

## Autonomous architect/builder continuation
- Builder plan: audit exact NumPy source/artifact inclusion, verify compatible image rebuild paths, then implement only documented scope amendments and collect complete independent checks. Preserve all prior evidence and policy gates; no commit or push.
- Hash-verified NumPy 2.4.2 source includes two CC0 notices. The splitmix64 references found so far are benchmark/data-generator sources; Highway random-inl is named by its own test/build metadata. A compiler dependency audit is required before calling a derivative wheel compliant.
- Selected bounded UI remediation replaces the licence-blocked wrapper/animation dependencies: exact Geist assets and original OFL notice retained; browser-native scroll/reveal module stays lazy and retains static reduced/narrow branches. The independently reconciled production closure shrinks to 236 identities and passes OSI validation. Initial unbounded Vitest run hit two async waits under concurrent compiler load; the unchanged suite passes all 207 with bounded workers. Browser startup exceeded its unchanged pre-seed deadline on the first attempt; preserve it and rerun after compiler completion.
- Completed the exact NumPy source/artifact audit: all 8,242 source files unmodified, full 229-unit compiler/header closure excludes both CC0 implementations, and the official wheel's 1,042-member and 21-library symbol inventory agrees with the selected source paths. The installed-artifact correction retains all notices and includes bundled LAPACK/GCC terms, with platform/wheel/member/bytecode/symlink guards and strict reviewed WITH handling. No locally built wheel is substituted; no blanket NumPy-version claim is made.
- The supported pg16 trixie variant passes the unchanged fixed-critical gate. Scratch physical restart proves collation drift; fresh logical restore passes data/vector/index checks. A new default pgdata_trixie volume and collation health guard preserve the old pgdata for rollback; migration instructions are in docs/postgres-upgrade.md.
- Official Grafana 13.2.4 distroless-slim avoids the critical embedded components of the full variant. Its exact image passes the same scanner threshold and starts with the existing provisioning/dashboard/Prometheus datasource configuration; AGPL notice hash verified. Follow the security-age exception and record functional limits rather than treating a version number as proof.
- The scanner now parses the same YAML image inventory as the pin checker, includes optional build-only services and all service Dockerfiles, records immutable output IDs and image CycloneDX artifacts, and continues independent checks after a failed service build. Grype consumes the captured immutable ID, preventing mutable-tag races.

- Architect final browser attempt exposed validation-environment interference: concurrently running integration fixtures delete platform cache keys, including browser sessions, in their own shared Valkey instance. Preserved failed browser output; isolated the browser suite on a separate test-owned Valkey container with the identical final image. No product code or assertions changed.
- Architect completed final source-age review using primary Go release history, official package/tag metadata and the Ollama release page. Documented security-age exceptions and exact scope in evidence/pins.txt; remaining golang.org/x module dates predate the cutoff. No release date was inferred from registry publication.
- Common image path completed with exit0: twelve immutable artifact scans pass the unchanged fixed-critical policy. Preserved every CycloneDX report and alias/identity ledger; independently verified runtime rootfs/platform/config equality with live-tested artifacts. Final Ruff and147-file mypy pass. Repaired validation runner, cache isolation and scheduling without changing any product/test assertion. Final full backend rerun starts after scan load clears; browser follows it.

## Round 2
Plan: address F1 through F6 in order with focused edits, add the requested regression coverage, run each Round 2a command, and save captured output under evidence/round2-*.txt. Preserve all unrelated working-tree changes and log any blocker while continuing.
- F1 done: lint, typecheck, eval and unit jobs run without change-scope gating; only integration/e2e, migration and the image scan consume scope. UI paths set both scopes, and the diff uses `--no-renames`; regressions cover scope and required jobs.
- F2 partially done, blocked on the real tree: removed PSF-2.0 from the OSI list, added the official SPDX OSI fixture and subset test, and limited the exception to exact `aiohappyeyeballs==2.6.1`. The fixture gate rejects BUSL-1.1 as required. The real gate also finds `typing_extensions==4.15.0` metadata labeled PSF-2.0; D2 does not authorize another exception. Recorded in `planning/QUESTIONS.md`.
- F3 done: pinned the UI Node and nginx images to older exact tags and Docker Hub digests; recorded tag metadata dates in `evidence/pins.txt`. Pin discovery includes all project Dockerfiles outside ignored scratch/dependency folders, and the image gate builds/scans the UI image.
- F4 done: preflight warns for each old/new volume pair without failing and adds selected profile ports. Added stub-engine warning/port tests and executable pgvector dump/restore commands in `docs/postgres-upgrade.md`.
- F5 done: optional services use the exact upstream pinned images; retained and mounted `s3.json` read-only; removed the three recipe folders (except `s3.json`), recipe-only build steps and docs. `--built-services` still discovers only `worker`; the app Dockerfile remains in the scan. Exception parser tests use fixture Compose files. `image-exceptions.txt` remains comment-only for the later live scan round.
- F6 done: corrected setup credentials and Valkey command text, ADR-0008 broker wording, sanitized MCP warnings, `LOG_LEVEL` test isolation, Kafka topic auto-creation and topic-init ordering. `license-checker-rseidelsohn` 5.0.1 and `@cyclonedx/cyclonedx-npm` 6.0.1 are exact pins at every npm invocation.
- Round 2a checks: Ruff passed; mypy passed (147 files); unit tier: 897 passed; Docker-CLI-only failures are `test_compose_profiles_render_with_loopback_ports[]`, `[models]`, `[streams]`, `[lake]` and `[observability]`; real licence gate blocked by the F2 issue; non-OSI fixture failed as expected; pin checker passed. Captured outputs are `evidence/round2-{ruff,mypy,unit,licence,licence-nonosi,pins}.txt`.
