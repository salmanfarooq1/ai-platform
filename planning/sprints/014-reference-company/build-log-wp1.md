# WP1 build log

## Plan
1. Write tests 1.1–1.6 before implementation, using the existing tenant fixtures.
2. Add the six persona definitions and private, validated credential setup through the identity CLI.
3. Run focused checks, attempt integration with the supplied environment, then run the Python gate once.

## Spec questions
- No evidence ignore-list file or evidence packaging consumer exists in the repository. Add `.evidenceignore` as the launch-authorized evidence ignore list; the Architect must apply it when collecting artifacts.
- Fixture ownership has no database marker. Require an explicit tenant slug and UUID plus an active fixture credential supplied through `SHOWCASE_FIXTURE_KEY`, and verify all three against the database before any write.

## Work
- Read the brief, common launch, winning addendum, WP1 blueprint/test specification, identity CLI/scopes, fixtures and ignore configuration. Sprint 013 changes are the base; WP2 files are untouched.
- Wrote tests 1.1–1.6 first, plus missing/mismatched state and tenant-credential verification regressions. Initial focused unit run failed collection with `ImportError: cannot import name 'personas' from 'scripts.showcase'`, before implementation existed.
- Added six persona JSON files, identity-CLI capture, tenant/credential verification, private atomic files, manifest validation, serialized reruns and explicit single-persona replacement. Added `.showcase/` to git, Docker and the new evidence ignore list. No new dependencies or tenant creation code.
- Focused checks: specified unit tests 1.4–1.6 passed (3 passed); live integration tests 1.1–1.3 and two additional regressions passed (5 passed), after sourcing `/home/ubuntu/ai-platform/scratch/env012.sh`. Shell syntax and focused/full Ruff passed. Focused mypy passed.
- Scope review: `query` already grants governed KB reads, so consumer carries only `query`. Added atomic-rename failure coverage and directory fsync for durable private writes.
- Hardened test assertions: compare keys and secret verification through boolean results, and inspect a standalone return code, so assertion diagnostics cannot expose private keys or captured subprocess output. Expectations are unchanged; no specified assertion was removed or weakened.

## Gate limitation for the Architect
- Ran the required full unit gate once. Existing Sprint 013 `tests/unit/test_models_live.py::test_live_digest_check_is_conditional` detects reachable Ollama and sends `/api/chat`; it failed with `TimeoutError: timed out` in `urllib.request.urlopen(request, timeout=60)`. This live behavior conflicts with the addendum's no-Ollama-model-load rule and was discovered from the failure. No retry of that test or manual model call was made. Its file is outside WP1's allowed scope and remains unchanged. The Architect must reconcile its tier/live behavior with that launch rule.
- Full unit result: 1 failed, 1047 passed, 916 deselected, 2 warnings. WP1 unit tests passed within that run. Full Ruff, mypy (172 source files), standalone persona mypy and six import contracts pass.

## Files changed
- Six JSON definitions in `data/reference-company/personas/`.
- `scripts/showcase/setup_personas.sh`, `scripts/showcase/personas.py`.
- `.gitignore`, `.dockerignore`, new `.evidenceignore`.
- `tests/integration/refco/test_personas.py`, `tests/unit/refco/test_personas_files.py`, this log.

## Usage and recovery
- In the existing Poetry environment, privately export `MIGRATION_DATABASE_URL` and `SHOWCASE_FIXTURE_KEY`; run `scripts/showcase/setup_personas.sh --tenant <fixture-slug> --tenant-id <fixture-uuid>`. Use `--replace <persona>` only for explicit replacement.
- Missing or inconsistent saved credentials stop setup before any new credential is issued. Replacement verifies the existing principal and all other personas first, revokes an active old key and creates exactly one new key. Missing principal/manifest identity requires owner inspection.
- A failure between committed CLI provisioning and private-state persistence fails closed. Existing persona names prevent duplicate provisioning; incomplete or inconsistent state requires owner inspection rather than automatic regeneration.
- Artifact collection must apply `.evidenceignore`; no existing evidence collector was found to wire it into within the allowed scope.

## Proposed human commit (do not run automatically)
```bash
git add .gitignore .dockerignore .evidenceignore data/reference-company/personas/ scripts/showcase/setup_personas.sh scripts/showcase/personas.py tests/integration/refco/test_personas.py tests/unit/refco/test_personas_files.py planning/sprints/014-reference-company/build-log-wp1.md
git commit -m "feat(identity): add private reference-company persona setup"
```

## Captured command output

Output excerpts below are captured from command results, not rewritten.

```bash
/home/ubuntu/.local/share/poetry233/bin/poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain scripts/showcase/personas.py
```

```text
All checks passed!
```

```bash
/home/ubuntu/.local/share/poetry233/bin/poetry run mypy
```

```text
Success: no issues found in 172 source files
```

```bash
/home/ubuntu/.local/share/poetry233/bin/poetry run mypy scripts/showcase/personas.py
```

```text
Success: no issues found in 1 source file
```

```bash
/home/ubuntu/.local/share/poetry233/bin/poetry run lint-imports
```

```text
Analyzed 161 files, 520 dependencies.
-------------------------------------

ports imports no platform package KEPT
core imports no module package KEPT
evidence does not import gateway, api or workers KEPT
gateway does not import evidence, api or workers KEPT
agent and MCP code do not import evidence KEPT
agent and MCP code use only the gateway package API KEPT

Contracts: 6 kept, 0 broken.
```

```bash
/home/ubuntu/.local/share/poetry233/bin/poetry run pytest -m unit -q
```

```text
=================================== FAILURES ===================================
____________________ test_live_digest_check_is_conditional _____________________
tests/unit/test_models_live.py:33: in test_live_digest_check_is_conditional
    with urllib.request.urlopen(request, timeout=60) as response:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/urllib/request.py:216: in urlopen
    return opener.open(url, data, timeout)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/urllib/request.py:519: in open
    response = self._open(req, data)
               ^^^^^^^^^^^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/urllib/request.py:536: in _open
    result = self._call_chain(self.handle_open, protocol, protocol +
../../.pyenv/versions/3.11.0/lib/python3.11/urllib/request.py:496: in _call_chain
    result = func(*args)
             ^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/urllib/request.py:1377: in http_open
    return self.do_open(http.client.HTTPConnection, req)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/urllib/request.py:1352: in do_open
    r = h.getresponse()
        ^^^^^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/http/client.py:1374: in getresponse
    response.begin()
../../.pyenv/versions/3.11.0/lib/python3.11/http/client.py:318: in begin
    version, status, reason = self._read_status()
                              ^^^^^^^^^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/http/client.py:279: in _read_status
    line = str(self.fp.readline(_MAXLINE + 1), "iso-8859-1")
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../.pyenv/versions/3.11.0/lib/python3.11/socket.py:705: in readinto
    return self._sock.recv_into(b)
           ^^^^^^^^^^^^^^^^^^^^^^^
E   TimeoutError: timed out
=============================== warnings summary ===============================
tests/unit/test_eval_gate.py::test_the_suite_scores_what_the_baseline_says
  /home/ubuntu/.cache/pypoetry/virtualenvs/ai-platform-dDxeGklu-py3.11/lib/python3.11/site-packages/pydantic/_internal/_generate_schema.py:1480: UserWarning: Item 'summary' on TypedDict class 'ChatCompletionReasoningItem' is using the `ReadOnly` qualifier. Pydantic will not protect items from any mutation on dictionary instances.
    warnings.warn(

tests/unit/test_search_route.py::test_search_request_defaults
  /home/ubuntu/ai-platform-sprints/014-reference-company/tests/unit/test_search_route.py:14: DeprecationWarning: deprecated
    assert req.rerank is True

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/unit/test_models_live.py::test_live_digest_check_is_conditional
1 failed, 1047 passed, 916 deselected, 2 warnings in 354.18s (0:05:54)
```

```bash
source /home/ubuntu/ai-platform/scratch/env012.sh
/home/ubuntu/.local/share/poetry233/bin/poetry run pytest tests/unit/refco/test_personas_files.py tests/integration/refco/test_personas.py -q -rs --tb=short
```

```text
.........                                                                [100%]
9 passed in 19.41s
```

```bash
/home/ubuntu/.local/share/poetry233/bin/poetry run ruff check scripts/showcase/personas.py tests/unit/refco/test_personas_files.py tests/integration/refco/test_personas.py
```

```text
All checks passed!
```

## Final WP1 result
- Tests 1.1–1.6 pass; all nine WP1 checks pass on the final files. No key was printed in the sentinel captures.
- Unfinished: Architect review of the existing live-Ollama unit failure and evidence collector convention, as documented above. No state-changing git command, Docker command or dependency installation was run.

## WP1 independent-review fix round

### Plan recorded before the fix
1. Treat amended rows 1.3, 1.5 and 1.7–1.10 as authoritative; write the new regressions and capture their failures before code changes.
2. Enforce explicit fresh-tenant claim and active fixture marker before any write, and restrict private state paths.
3. Journal issuance intent without secrets, detect interrupted issuance and recover only the explicitly replaced persona; test both interruption points and secret-free diagnostics.
4. Remove the unused `.evidenceignore`, run focused unit/integration checks and Ruff, and record captured results here. Leave WP2 and owner files untouched.

### Tests before code
- Updated row 1.5 to require git/Docker exclusion, absence of `.evidenceignore`, and a platform-key-pattern scan of every `planning/**/evidence/` file. It failed on the obsolete ignore file before implementation.
- Added exact named rows 1.7–1.10: missing/disabled markers, fresh/default tenant claim, non-fresh principal/document/policy rejection, admin-only claim, protected paths, both failure points during initial issuance and replacement, and sentinel scans of stdout/stderr/logs/private metadata.
- Initial red run: 14 failed, 2 passed. The document branch exposed missing fixture columns; the failure-sentinel branches passed accidentally on a duplicate prefix. Before code changes, corrected `document_id` and made generation unique after the sentinel's first key. The marker/failure subset then failed all 10 cases against the old implementation: missing/disabled marker acceptance, unsupported claim, and absent interruption hooks; the document branch still had a fixture schema error. The first implementation run exposed its required `embedding_model`/`embedding_dim`, which were added without changing the expectation. All four recovery cases and both ignore/path cases failed before code changes. A later symlink-path regression failed with `DID NOT RAISE SetupError` before its fix.
- Preserved all pre-existing assertions except the `.evidenceignore` expectation explicitly superseded by row 1.5. Kept all new failure assertions; no skips, xfails or scan exclusions.

### Implementation
- `personas.py`: explicit `--claim` creates only the `refco-fixture-owner` service principal in a fresh tenant with the caller's active admin credential. The freshness check holds table locks, allows only the caller's principal, and rejects documents and stored policy versions. The platform default has no stored policy row. Normal setup requires exactly one active service marker before any filesystem write. A disabled marker cannot be silently reclaimed.
- `--state-dir`: accepts only repo `.showcase/` or an absolute external path; rejects an `evidence` path component, symlinks and foreign-owned destinations before writes.
- Intent journal: stores only tenant/database, persona, principal id and key prefixes, durably before principal creation or key issuance. Reruns name the interrupted persona and require its explicit replacement. Recovery checks every unaffected persona, revokes the orphan and issues exactly one replacement for the affected principal. Completed personas retain their keys. Old published keys remain active until both new files are written; caught interruptions restore the previous matching pair. Recovery also tolerates a mismatched pair left by an abrupt interruption.
- Test-only hooks: `SHOWCASE_TEST_FAIL=after_key:<persona>` and `between_renames:<persona>`. The variable is read only when `pytest` is in `sys.modules` and `PYTEST_CURRENT_TEST` is set. Standalone subprocesses ignore it; row 1.3 tests that behavior. The hooks, journal and error messages never contain a token. Tests assert matching intent exists before every issuance.
- `setup_personas.sh`: documents and forwards `--claim`/`--replace`; tracing stays off. Deleted the unused `.evidenceignore` as requested. No schema or migration change.

### Open point: inherited evidence patterns
- Row 1.5 now correctly fails on 25 tracked historical evidence files in Sprints 003, 006, 011 and 012. These artifacts are outside the WP1 launch's allowed files. They were not modified; no owner's untracked file was touched. Matched values were never printed or copied into logs. The path-only inventory is captured below for the Architect to authorize/perform historical evidence redaction.
- This supersedes the original proposal to rely on `.evidenceignore` and the original credential-only fixture proof. The earlier proposed commit command is historical; the current proposal includes only `scripts/showcase/personas.py`, `scripts/showcase/setup_personas.sh`, both WP1 test files and this log.

### Captured fix-round checks

```text
Red: amended ignore/path/recovery tests, before implementation
FAILED tests/unit/refco/test_personas_files.py::test_ignored_everywhere - Ass...
FAILED tests/unit/refco/test_personas_files.py::test_state_dir_must_be_protected
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[missing]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[revoked]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[fresh]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[default]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[principal]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[documents]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[policy]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[nonadmin]
FAILED tests/integration/refco/test_personas.py::test_interrupted_run_is_recoverable[True-after_key]
FAILED tests/integration/refco/test_personas.py::test_interrupted_run_is_recoverable[True-between_renames]
FAILED tests/integration/refco/test_personas.py::test_interrupted_run_is_recoverable[False-after_key]
FAILED tests/integration/refco/test_personas.py::test_interrupted_run_is_recoverable[False-between_renames]
14 failed, 2 passed in 17.60s
```

```text
Red: corrected sentinel tests and marker/claim cases, before implementation
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[missing]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[revoked]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[fresh]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[default]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[principal]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[documents]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[policy]
FAILED tests/integration/refco/test_personas.py::test_refuses_non_fixture_tenant[nonadmin]
FAILED tests/integration/refco/test_personas.py::test_keys_never_printed_on_failure[after_key]
FAILED tests/integration/refco/test_personas.py::test_keys_never_printed_on_failure[between_renames]
10 failed in 11.57s
```

```text
Red: symlink-path regression, before its fix
F                                                                        [100%]
=================================== FAILURES ===================================
_______________________ test_state_dir_must_be_protected _______________________
tests/unit/refco/test_personas_files.py:103: in test_state_dir_must_be_protected
    with pytest.raises(personas.SetupError, match="symlink"):
E   Failed: DID NOT RAISE SetupError
----------------------------- Captured stderr call -----------------------------
FAIL personas: state directory must be repo .showcase or an absolute path outside the worktree
FAIL personas: private state cannot have an evidence path part
FAIL personas: private state cannot have an evidence path part
FAIL personas: state directory must be repo .showcase or an absolute path outside the worktree
FAIL personas: private state cannot have an evidence path part
=========================== short test summary info ============================
FAILED tests/unit/refco/test_personas_files.py::test_state_dir_must_be_protected
1 failed in 5.20s
```

```text
/home/ubuntu/.local/share/poetry233/bin/poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain scripts/showcase/personas.py
All checks passed!
```

```text
/home/ubuntu/.local/share/poetry233/bin/poetry run mypy scripts/showcase/personas.py
Success: no issues found in 1 source file
```

```text
/home/ubuntu/.local/share/poetry233/bin/poetry run pytest -m unit tests/unit/refco/test_personas_files.py -q --tb=short
.F...                                                                    [100%]
=================================== FAILURES ===================================
___________________________ test_ignored_everywhere ____________________________
tests/unit/refco/test_personas_files.py:81: in test_ignored_everywhere
    assert not leaked_paths, "platform key pattern found in evidence (contents withheld)"
E   AssertionError: platform key pattern found in evidence (contents withheld)
E   assert not ['planning/sprints/006-ports-adapters/evidence/pytest-int-e2e.txt', 'planning/sprints/011-baseline-and-stack/evidence/...k/evidence/rework-skips-unavailable.txt', 'planning/sprints/011-baseline-and-stack/evidence/pytest-int-e2e-a.xml', ...]
=========================== short test summary info ============================
FAILED tests/unit/refco/test_personas_files.py::test_ignored_everywhere - Ass...
1 failed, 4 passed in 7.81s
```

```text
source /home/ubuntu/ai-platform/scratch/env012.sh
/home/ubuntu/.local/share/poetry233/bin/poetry run pytest -m integration tests/integration/refco/test_personas.py -q -rs --tb=short
...................                                                      [100%]
19 passed in 21.22s
```

Historical evidence inventory (paths only; captured scan output):

```text
tracked planning/sprints/003-identity-tenancy/evidence/pytest-int-e2e.txt
tracked planning/sprints/003-identity-tenancy/evidence/qa-secrets-grep.txt
tracked planning/sprints/006-ports-adapters/evidence/pytest-int-e2e.txt
tracked planning/sprints/011-baseline-and-stack/evidence/architect-final-unit.xml
tracked planning/sprints/011-baseline-and-stack/evidence/autonomous-unit.xml
tracked planning/sprints/011-baseline-and-stack/evidence/baseline-pytest.xml
tracked planning/sprints/011-baseline-and-stack/evidence/finish-integration-final.txt
tracked planning/sprints/011-baseline-and-stack/evidence/finish-integration-final.xml
tracked planning/sprints/011-baseline-and-stack/evidence/finish-integration-first.xml
tracked planning/sprints/011-baseline-and-stack/evidence/finish-integration-interrupted.xml
tracked planning/sprints/011-baseline-and-stack/evidence/finish-integration-verified.txt
tracked planning/sprints/011-baseline-and-stack/evidence/finish-integration-verified.xml
tracked planning/sprints/011-baseline-and-stack/evidence/finish-unit.xml
tracked planning/sprints/011-baseline-and-stack/evidence/pytest-int-e2e-a-before-wait-fix.xml
tracked planning/sprints/011-baseline-and-stack/evidence/pytest-int-e2e-a.xml
tracked planning/sprints/011-baseline-and-stack/evidence/rework-final-unit.xml
tracked planning/sprints/011-baseline-and-stack/evidence/rework-int-e2e-before-final.xml
tracked planning/sprints/011-baseline-and-stack/evidence/rework-int-e2e-unavailable.xml
tracked planning/sprints/011-baseline-and-stack/evidence/rework-int-e2e.xml
tracked planning/sprints/011-baseline-and-stack/evidence/rework-skips-unavailable.txt
tracked planning/sprints/011-baseline-and-stack/evidence/rework-unit.xml
tracked planning/sprints/012-pillars-and-boundaries/evidence/after-move-combined.xml
tracked planning/sprints/012-pillars-and-boundaries/evidence/after-move-unit.xml
tracked planning/sprints/012-pillars-and-boundaries/evidence/behavior-unit-current.xml
tracked planning/sprints/012-pillars-and-boundaries/evidence/final-unit.xml
```

### Fix-round result
- Final focused integration: 19 passed. Final focused unit: 4 passed, 1 failed (row 1.5 historical evidence scan). Ruff, standalone mypy and shell syntax pass.
- Row 1.5 remains open pending historical evidence redaction outside WP1 scope; its scan is intact. No other WP1 failure remains. No full unit suite or live model test was rerun.
- Files changed this round: both showcase setup files, both WP1 test files, this log; removed `.evidenceignore`. WP2 and owner files were not edited.

## WP1 fix round 2 plan
1. Add real process-death, parser-value and nested pytest leak regressions; capture red before implementation.
2. Make denied crash recovery quarantine a torn key/manifest pair, without issuing or revoking credentials; preserve explicit replacement and the private intent fence.
3. Drain stdout/stderr and both pytest log capture handlers before any sentinel assertion. Inject a known issued sentinel plus the fixture admin credential into success/failure checks, including shell traces and private metadata.
4. Run Ruff, mypy on changed Python files and both refco test folders. Preserve the Architect's entire unit test file, including the row 1.5 exemption.

### Fix round 2 changes
- Added two real `os._exit(73)` subprocess cases at `between_renames`, covering initial issuance and replacement. Before code changes, both failed because a denied rerun left the published pair mismatched. They now prove that the rerun names the persona and changes no principal/key count, its quarantine leaves a matching published pair, explicit replacement revokes the orphan and issues exactly one replacement with one active key, and subsequent setup reuses state.
- Kept the existing private intent fence and two regular output files. A real death can bypass rollback and leave a torn pair. The next setup validates every unaffected persona, quarantines only the pending persona from a torn pair, and returns a deny while retaining the intent. It does not issue or revoke a key until explicit replacement. This repair is idempotent if interrupted again; it does not claim filesystem-wide atomicity across both files.
- Added a private argparse subclass with a fixed program name and a fixed error message. Bad argument values never reach parser stderr. The regression supplies a generated sentinel as an invalid `--replace` value and verifies exit 2 without echoing it.
- Added two nested pytest regressions that deliberately inject a synthetic credential into stdout, stderr and log capture, then inspect the child failure report without printing its captured text. Both failed red against the old success/failure checks. They now pass while the child assertions still fail as intended.
- All sentinel checks now read stdout/stderr, snapshot logs and clear BOTH pytest LogCaptureHandlers (fixture and failure-report handlers) before asserting anything about status or secrets. A match fails through `pytest.fail(..., pytrace=False)` with fixed withheld-content text. Crash assertions use safe local IDs/boolean results so pytest does not render credential-bearing fixture representations.
- Tightened row 1.3: a test-owned Python shim injects a known key into real issuance behind the actual `bash -x` wrapper. The active fixture admin credential is a second sentinel; the original fixture key and other issued keys are also retained in scans. Success and both failure boundaries scan subprocess stdout/stderr, pytest capture, log files, actual shell traces and private metadata. The known prefix is verified in the database; success verifies its token was saved privately. An interrupted first issuance must leave no sentinel in any private state file, including keys.env. Test shims contain no literal token; values travel only through the private test environment.
- Mypy on both changed Python files required `--explicit-package-bases` for namespace packages. Added explicit non-null database-row checks instead of indexing an optional result; all existing result expectations remain intact.
- Files changed: `scripts/showcase/personas.py`, `tests/integration/refco/test_personas.py`, this log. The full SHA-256 of `tests/unit/refco/test_personas_files.py` matches its pre-round snapshot; lines 75–89 and the Architect's fixture exemption are untouched. WP2 files were not edited. No commit, dependency installation, schema change or real model call.

### Fix round 2 captured checks

Red regressions, before implementation:
```text
FAILED tests/integration/refco/test_personas.py::test_process_death_between_renames_is_recoverable[True]
FAILED tests/integration/refco/test_personas.py::test_process_death_between_renames_is_recoverable[False]
FAILED tests/integration/refco/test_personas.py::test_parser_errors_do_not_echo_argument_values
FAILED tests/integration/refco/test_personas.py::test_sentinel_assertion_failure_does_not_echo_capture[test_keys_never_printed]
FAILED tests/integration/refco/test_personas.py::test_sentinel_assertion_failure_does_not_echo_capture[test_keys_never_printed_on_failure]
5 failed, 19 deselected in 34.08s
```

```text
First WP1 integration run after the fixes
........................                                                 [100%]
24 passed in 54.88s
```

```text
/home/ubuntu/.local/share/poetry233/bin/poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain scripts/showcase/personas.py
All checks passed!
```

```text
/home/ubuntu/.local/share/poetry233/bin/poetry run mypy --explicit-package-bases scripts/showcase/personas.py tests/integration/refco/test_personas.py
Success: no issues found in 2 source files
```

```text
source /home/ubuntu/ai-platform/scratch/env012.sh
/home/ubuntu/.local/share/poetry233/bin/poetry run python -m pytest tests/unit/refco tests/integration/refco -q -rs --tb=short
(test output captured in memory and key-pattern-redacted before writing the result file)
.....................................                                    [100%]
37 passed in 108.49s (0:01:48)
```

### Fix round 2 result
- Five new regression cases failed red for the identified reasons; all 24 WP1 integration cases pass after the fixes. Final combined refco folders: 37 passed, no failures or skips. Ruff and mypy pass; shell syntax and the unchanged unit-file hash were verified.
- No open WP1 point from this round. The previous row 1.5 open point is superseded by the Architect's unchanged fixture exemption, which passes in the combined run.
