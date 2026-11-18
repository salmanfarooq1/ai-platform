ACCEPT (no blocking findings; 2 LOW follow-ups)

# WP4 fix round 2: independent review

Reviewer: Claude Opus (cross-model; the builder was Sonnet). The review was read-only. No Docker and no live runs.

## Checks run
- `pytest tests/unit/refco tests/unit/test_poc*.py`: 478 passed.
- ruff on `scripts/poc_lib`, `poc_drill.py`, `test_poc_fix2.py` and `tests/unit/refco`: clean.
- mypy `--explicit-package-bases scripts/poc_lib scripts/verify/poc_drill.py`: clean (8 files).
- lint-imports: 7 contracts kept.
- Test-ID diff, `evidence/wp4-unit.xml` (1518) against the current collect (1596, function level):
  - Only one ID is missing: the test that was intentionally inverted in fix 1.
  - 41 new test functions.
  - No skip or xfail markers in the changed tests.
- Red evidence (`wp4-fix2-red.txt`) is consistent with the code: 22 scanner reds, 17 fix2 reds, and the phase and destroy-lock mutants.

## Items
1. **M1 scanner: CLOSED for the stated forms** (`tests/unit/refco/test_public_seams.py:150-206`).
   - A probe confirmed the following are flagged: `h.post` (aliased), `urllib.request.urlopen` (nested), `ur.urlopen` and `request.urlopen`, any module (`json`, `os.path`, a product module), the AugAssign, AnnAssign and setattr forms, and imports inside a function.
   - The real sources stay clean, and local-object attribute writes are not flagged.
2. **L1: CLOSED.**
   - `poc_drill.py:362-363` fails cleanly on a missing phase.
   - The tests compare the full FAIL line (`test_m0_lifecycle.py:585-609`).
   - The phase-default mutant now goes red against the exact message.
3. **L3: CLOSED.**
   - `validate_ollama_url` (`up.py:59-71`) allows only http or https with a host. It rejects credentials, a query, a fragment, whitespace and non-ASCII, caps the length at 200 and rejects a bad port.
   - A `file:`, `ftp:` or credentialed value is refused before any state exists.
   - The stored file is lstat-checked (regular file, 0600, own uid), re-validated on read, and written atomically with O_EXCL and O_NOFOLLOW.
   - The environment wins, a load never rewrites the file, and the next `up` persists the value. These semantics are sensible.
   - SSRF is not a concern: this is operator configuration that only reaches Compose.
4. **L4: CLOSED.**
   - `_reload_after_lock` (`lifecycle.py:59-62`) runs the private-folder check plus `load_context`. It is used by `backup` (`:70`) and `down` (`:100`).
   - The RealBackend is built from the reloaded context.
   - Tests mutate the state inside the lock and show that capture and backend are never reached.
5. **L5: CLOSED.** The `context.py` docstring and the lock message now say `up` waits while `backup`, `down` and `destroy` refuse.
6. **L6: CLOSED and safe.**
   - `created_here` is set only under `--create-only`, after the `lexists` and leftover-volume checks, and it is decided under the waiting lock (`up.py:283-289`).
   - Cleanup runs only while the marker is not yet written (`:313-315`). It runs under the lock, re-checks the private dir, and uses `shutil.rmtree`, which refuses a symlinked top-level folder.
   - There is no race with a concurrent creator: every writer into `.poc/<stack>` (up, backup, down, restore, catalog, pending) runs under the same lifecycle lock, and `up` waits on it. A pre-existing folder is never removed (there is a test for this).
7. **Destroy-lock red: CLOSED.** The red run is captured: the mutant (rmtree moved outside the lock) fails `assert False is True`.
8. **L2: kept `0.0.0.0` with a reasoned comment** (`poc_drill.py:100-104`).
   - It was not tried live. The "172.17.0.1" claim is environment-specific: under Docker Desktop, host-gateway is proxied.
   - The Architect's live drill should still try 127.0.0.1 once.

## Rule 10
- The drill and journey have no private imports, no product SQL and no global overrides. The scanner passes on all real sources.
- The new URL seam is public operator config.

## Follow-ups (LOW, non-blocking)
- **L-a. The scanner can still be evaded deliberately** (`test_public_seams.py:180-195`). None of these forms is flagged:
  - tuple targets (`h.post, h.get = ...`);
  - `del httpx.post`;
  - `for httpx.post in ...`;
  - rebinding (`x = httpx; x.post = ...`);
  - `sys.modules['httpx'].post = ...`;
  - `importlib.import_module(..).post = ...`;
  - `object.__setattr__`;
  - `vars(m)[..]` and `m.__dict__[..]`.

  Cheap wins:
  - walk Tuple and List targets;
  - handle `ast.Delete` and For targets;
  - treat a `sys.modules[...]` root or an `import_module(...)` root as a module.

  There is also one benign false positive: a parameter that shadows a module name (`def f(json): json.x = 1`).
- **L-b. The URL in the environment is validated only in `up`.** `compose_env` (`up.py:168`) passes the environment value through unvalidated for `backup` and `down`, so a malformed value can reach the writers' restart after a refused `down`. Fix: validate it in `compose_env` too. The value is operator input, so this is low risk.
