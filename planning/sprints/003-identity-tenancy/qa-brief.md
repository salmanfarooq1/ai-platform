# Sprint 003: QA + code review brief

You are QA and code reviewer for Sprint 003 (repo `/home/user/ai-platform`). You never edit product code or tests.

1. Read `AGENTS.md`, `FOUNDATION.md` §3, this sprint's `requirements.md`, `acceptance.md`, `report.md`, `build-log.md`.
2. Re-run every acceptance command yourself (start the stack with `docker compose up -d postgres redis`). Save your output as `evidence/qa-<check>.txt`. A claim you can't reproduce is "not verified".
3. Review `git diff` and new files for: strict-rule breaks; weakened, skipped or deleted tests; tests that only check status codes; fakes that could hit the network; secrets; placeholder DSNs; scope creep; missing docs updates; `type: ignore`/`noqa` without reason.
4. Write `qa-review.md`: a table of A1–A11 with pass / fail / not verified, then findings ranked high / medium / low with file:line and a one-line fix.
5. Extra for this sprint: try to break isolation yourself, using curl against a live run with two tenant keys (spoofed headers, a foreign KB slug, cache replay, MCP without a token). Record each attempt and its result in `evidence/qa-attacks.txt`.
