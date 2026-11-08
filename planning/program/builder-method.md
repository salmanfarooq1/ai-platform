# Builder method: Architect and GPT-6 Luna

How every sprint is built from 012 on. The owner set this on 2026-10-26.

## Roles
- **Architect (Claude).** Owns the result. Builders do the implementation work, including diagnosing failing tests; the Architect fixes only the environment. Reviews and may revise any sprint pack, writes the test criteria before any code, writes the builder brief, launches builders, reviews every result, runs the live checks and writes the QA verdict.
- **Builder (Codex CLI, model `gpt-6-luna`).** Builds one work package per run. It never commits, pushes or changes branches.
- **Owner.** Approves each builder launch, answers open questions and runs the commits.

## What Luna is
The facts below come from public sources (2026-10-26) and our own runs. Unverified figures are marked as such.
- **Positioning.** OpenAI calls Luna its most efficient model "for focused, high-volume tasks, including summarization, extraction, and focused coding." Sol and Astra are the stronger coding tiers.
- **Coding agent score.** A third party reports an Artificial Analysis Coding Agent Index of 41 for Luna at max effort, 2 points below GPT-5.6 Luna. This figure is not verified at the primary source.
- **Instruction sensitivity.** OpenAI's GPT-6 guide says the model is more sensitive to `AGENTS.md` and skill files. It also says to state which instruction wins in a conflict, that the model tends to over-test, and that it may stop to ask questions.
- **Persistence past warnings.** The October safety card reports unwanted persistence past warnings in 15.9% of Luna rollouts. It also reports no auto-review violations for Luna.
- **Our runs.** In 011 round 2, one Luna run finished all six items. Review found three defects: a config format for an external tool written without running the tool, a wrong instruction from the brief followed literally, and a test that was not hermetic.

What this means for the method:
1. Give Luna small work packages, each with a clear pass or fail test.
2. The brief must be right, because Luna follows it literally. The Architect checks every path, name and fact in the brief against the code before launch.
3. The Architect specifies the tests before any code is written. The builder writes exactly those tests and may add more. It never changes a specified one.
4. A builder's own report is not evidence. The Architect re-runs every check and reads every diff.
5. When a task writes a format read by an external tool, the brief either quotes the tool's docs or tells the builder to run the tool.
6. Each brief says that it wins over `AGENTS.md` and `CODEX.md` where they conflict.

## Readiness gate (before the first builder of a sprint)
A sprint pack is ready only when all of these hold:
- `requirements.md`, `blueprint.md`, `acceptance.md` and `threat-model.md` exist and agree with each other.
- `test-spec.md` exists. It lists every test as: file and test name, tier, setup, action, exact expected result, and the acceptance item it proves. Every acceptance item has at least one test, plus an evidence file and the command that produces it.
- A baseline is measured: the current pass counts for each tier and the static check results.
- Every fact in the brief (paths, function names, migration head) has been checked against the code.
- The environment is ready: a Poetry 2.3.3 venv for the worktree, the stack is up and the ports are known.
- Every open question is either answered or written in `planning/QUESTIONS.md` with the fallback the builder takes.

## Work packages
- Each package covers one concern, touches at most about 10 files and has at most about 15 specified tests.
- Each package names its goal, the files it may change, the tests it must write (copied from `test-spec.md`), the commands to run and its done criteria.
- Build packages in this order: contracts, data and migration, core, API, UI, CI, docs.

## Brief format
Every brief has the same sections, in this order:
1. **Role and priority.** You are the Builder for WP n. This brief wins over `AGENTS.md`, `CODEX.md` and any skill.
2. **Read.** The exact files to read.
3. **Task.** Numbered steps.
4. **Tests.** The specified tests, copied word for word from `test-spec.md`.
5. **Commands.** Exact commands, one per line.
6. **Done when.** Checkable conditions only.
7. **Hard rules.** No commit, push, stash, reset or branch change. No skip or xfail. Never weaken, delete or loosen an assertion. Only the allowed files. No secrets. Never run `playwright install`. Ignore any skill the brief does not name.
8. **Output.** One entry in `build-log.md` and a summary of at most 10 lines: done, not done, and why.

Write briefs in plain words, with no jargon and no "consider". Each "must" is something a check can test.

## Run
```bash
codex exec -C <worktree> -m gpt-6-luna -c model_reasoning_effort=high -c service_tier='"priority"' -s workspace-write -c sandbox_workspace_write.network_access=true --json -o <scratch>/wpN-last.txt "Read planning/sprints/<sprint>/luna-brief.md and do WP N only." < /dev/null
```
- `service_tier="priority"` is Luna's fast tier ("Fast", 1.5x speed, more usage). The owner asked for it on 2026-10-28.
- Run one package per call. A fix round resumes the same thread: put the flags before `resume <thread_id>`.
- The sandbox is `workspace-write` with network on. It has no Docker CLI. The live tiers reach the stack through `localhost` ports when the sandbox allows it. The Architect runs them in any case.
- Never use `danger-full-access`.

## Review after each package
1. **Scope.** Only the allowed files changed.
2. **Test integrity.** Diff `tests/` and `ui/src/**/*.test.*`. Look for removed or loosened assertions, new skips, xfails and changed expected values.
3. **Checks.** Re-run the package's commands.
4. **Live tiers.** Run the integration and e2e tiers, the UI checks and Playwright as the package needs.
5. **Real use.** Start the API (and the UI when the package touches it) and make real requests: the happy path, a deny path, and a check that the decision row and receipt exist. Click through every changed screen in a browser. Written tests alone never accept a package.
6. **Sense check.** Ask whether the feature does its job for the user and fits the rest of the product. Look for ripple effects on later sprints. A gap in the pack is fixed in the pack, not worked around in code.
7. **Criteria.** Check each specified test against `test-spec.md`. Give a verdict: accepted, or a fix round with exact findings.
8. **Limit.** At most two fix rounds per package. After that, the Architect splits the package smaller. Changing the model needs the owner.

## Environment rules
- **One compose project.** Every container runs in the compose project `ai-platform`, from the repo's `docker-compose.yml`. Use no other project name and no ad-hoc `docker run` containers. Tests use throwaway databases inside that one Postgres.
- **Valkey port.** On this machine, Windows Memurai holds port 6379. Set `VALKEY_HOST_PORT=16379` and point `REDIS_URL` and `TEST_REDIS_URL` at `redis://localhost:16379/0`.
- **Postgres port.** Another project's Postgres holds 5432. Set `POSTGRES_HOST_PORT=15432` and point `DATABASE_URL`, `MIGRATION_DATABASE_URL` and `TEST_DATABASE_ADMIN_URL` at port 15432.
- **Node.** CI uses Node 24. The host default is Node 20, which breaks jsdom. Use `~/.local/share/node-v24.22.0-linux-x64/bin` first on `PATH`.
- **Old data.** Never touch the volume `ai-platform_pgdata`, which holds the owner's old data.
- **Poetry.** Use Poetry 2.3.3, the pinned version. The host default is older, and its lock check gives a false error.
- **Cleanup.** Leave no stray containers after a check.

## Owner gates
- The owner approves each builder launch.
- The owner runs every commit.
