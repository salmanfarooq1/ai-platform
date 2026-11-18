ACCEPT (with 1 MEDIUM and 6 LOW follow-ups; none blocks the WP)

# WP4 fix round 1: independent review

Reviewer: Claude (cross-model; the builder was Sonnet, partly on top of an earlier Codex attempt). The review was read-only. No Docker and no live runs.

## Checks run
- Targeted unit tests: `pytest tests/unit/refco tests/unit/test_poc*.py` gave 434 passed.
- ruff on the changed scripts and tests: clean. lint-imports: 7 contracts kept. mypy on `scripts/verify/poc_drill.py` and `scripts/poc_lib`: clean.
- No skip or xfail markers in the changed tests.
- Test-ID diff, old `evidence/wp4-unit.xml` (1518 tests) against the current unit tier (1552):
  - Exactly one test function is gone: `test_a_stack_without_a_local_model_runtime_denies_at_admission_by_digest_and_the_drill_accepts_it`. That is intended. Its old behaviour (accepting a digest deny) is now the failure case, covered by `tests/unit/refco/test_m0_lifecycle.py:585`.
  - Every other "missing" ID is a parametrize-ID escaping difference between the junit XML and the collect-only output. The seeded cases are still present (`test_public_seams.py:226-255`).
- Not verified: the "four ruff auto-fixes in test files". The files are untracked, so there is no baseline to diff against. The Architect should diff them against the pre-round snapshot if one exists.

## The five findings
1. **Alias deny is CLOSED.**
   - The drill requires exactly `model_not_allowed` on the decision row (`scripts/verify/poc_drill.py:348`) and on the receipt (`:357`). It also requires the phase to be `admission` with no default (`:357`) and the alias to match (`:359`).
   - It also requires zero runtime calls, zero usage requests and policy denials (`:368-380`).
   - All of this is read through public HTTP seams.
2. **Ownership is CLOSED.**
   - Exit 3 means only that the stack is absent (`scripts/poc_lib/context.py:75-76`, `up.py:350-358`). A Docker failure gives exit 1.
   - `--create-only` is decided under the waiting lock (`up.py:238-251`).
   - The token comes only from the environment, is written first with 0600 and O_NOFOLLOW, and is checked by `destroy` before any removal (`lifecycle.py:166-208`).
3. **The destroy lock is CLOSED.**
   - The lock lives at `.poc/.locks/<stack>.lock`, outside the folder being deleted.
   - It is held through volume removal, image removal and the rmtree.
   - After the lock is taken, the private directory and the context are revalidated (`lifecycle.py:182-208`).
4. **The strict scanner is CLOSED for the stated scope.**
   - m0.py, the helpers, m0.sh and poc-drill.sh are scanned.
   - Each file class goes red on a seeded violation (`tests/unit/refco/test_public_seams.py:290-327`).
   - The scanner's generality is partial; see M1.
5. **The lock docs are CLOSED.** `docs/operations.md` says `up` waits while backup, down and destroy refuse. It also gives the lock path, the exit-3 meaning, `--create-only` and the token. For a small wording slip, see L5.

## Ranked follow-ups
- **M1. Gaps in the scanner's global-override detection** (`tests/unit/refco/test_public_seams.py:150-195`).
  - Only `Name.attr` targets are caught, and only when the name is an SDK alias or exactly httpx, requests, urllib3 or socket.
  - These would not be caught:
    - `import httpx as h; h.post = ...` (aliases are tracked only for SDK modules);
    - `urllib.request.urlopen = ...` (a nested attribute);
    - assigning to an attribute of an imported product module in a journey file, where product imports are allowed.
  - Fix: track the aliases of every import, resolve dotted chains, and flag any assignment to an attribute of an imported module. Add three seeded cases.
- **L1. The drill tests are weak on messages** (`tests/unit/refco/test_m0_lifecycle.py:585-597`).
  - They assert only `startswith("FAIL deny receipt saved")`.
  - Mutant "phase default": a None phase still fails, but through a KeyError at `poc_drill.py:364`. The test passes for the wrong reason.
  - Fix: assert "admission phase" or the reason in the message.
  - Mutant "digest accepted": effectively equivalent, because `:348` and `:357` each require `model_not_allowed` independently. This is acceptable defence in depth.
- **L2. The MetadataRuntime binds to 0.0.0.0** (`poc_drill.py:104`).
  - WSL runs in mirrored networking mode, so the port also listens on the LAN address for about 3.5 minutes.
  - What it exposes: only the public model digests, plus unbounded threads.
  - An outside peer can only raise the request counter. That causes a false FAIL, never a false PASS.
  - Architect, live: try a 127.0.0.1 bind (mirrored mode plus host-gateway may reach it). If it works, switch to it.
- **L3. `POC_OLLAMA_BASE_URL` is not persisted** (`docker/poc.override.yml`).
  - The default matches the product default (`core/settings.py:147`). `:-` covers an empty value, and the docs say "set it on every up".
  - Catch: a refused `down` restarts the writers through the compose `up` without the variable, so they come back with the default URL.
  - Fix: store it in the marker, or document the catch.
- **L4. `backup` and `down` load the context before taking the lock** (`lifecycle.py:65-66`, `:96-97`), so they do not revalidate after the lock. `destroy` does this correctly. Make the other two match.
- **L5. The docs say restore refuses, but it waits.**
  - The `lifecycle_lock` docstring and the message at `context.py:101` say "restore" refuses.
  - In fact restore runs inside `up`, which waits.
- **L6. A failed create-only can leave a folder behind.** If `--create-only` fails before the marker is written, `.poc/<stack>` is left behind. `status` then exits 1, so the drill does not tear it down. This is safe but leaves state. Fix: clean up the folder on early failure.

## Scrutiny points
- a. The 0.0.0.0 bind: see L2.
- b. The `POC_OLLAMA_BASE_URL` seam is compose-level operator configuration, a public seam a second client would use. It does not break Rule 10. It is safe when unset (it falls back to the product default) and is tested in `tests/unit/test_poc_compose.py:161`. For the persistence catch, see L3.
- c. Surviving mutants: see L1. The other 4 mutants were killed (`evidence/wp4-fix1-red-drill-mutants.txt`).
- d. The owner token is good:
  - `secrets.token_hex(16)` (128 bits) is checked with `hmac.compare_digest`;
  - the file is 0600, opened with O_NOFOLLOW and checked for the current uid;
  - the token travels only in the environment and never on argv, and it is scrubbed from the drill output (`poc_drill.py:155`);
  - it does reach the docker compose child's environment (`up.py:134-139`) but not the containers;
  - a stack without a token is refused only when a token is supplied; a plain `destroy` is unchanged.
- e. No test was weakened, skipped or deleted, apart from the intended inversion above. The ruff auto-fixes were not verified (no baseline).
- f. Rule 10: the drill has no private imports, no product SQL and no global overrides.

## Builder-declared deviations (accepted, but the Architect should cover them)
- The drill tests were written after the code.
- The destroy-lock regression test has no red run.
- m0.sh was not re-run live. The Architect should re-run the live drill and m0.sh.
