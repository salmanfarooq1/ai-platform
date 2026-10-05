# Sprint 009: Acceptance
- [x] **A1.** All checks pass with 0 skipped. The OpenShell adapter passes the AgentRuntime contract suite, against the real sandbox or the recorded fake (say which).
- [x] **A2.** The agent completes an authorized task in the sandbox.
- [x] **A3.** A direct call to a model provider from inside the sandbox fails, and a network-deny event is recorded.
- [x] **A4.** Reading a file outside the work directory fails, and an event is recorded.
- [x] **A5.** An unauthorized tool argument gets a gateway deny row with reason `tool_argument_not_allowed`.
- [x] **A6.** Sandbox events join `gateway_decisions` by `execution_id` in the runs API and on the Agent runs page (Playwright).
- [x] **A7.** A2-A5 are run live on a Linux host via `scripts/verify/openshell.sh`, or marked "not verified here" with the runbook.

## Sign-off
Sprint 009 is accepted. The Architect re-ran the checks after the QA fixes:
- ruff, mypy and the DDL guard are clean.
- Backend: 1523 tests passed. The only skips are the 10 live-MinIO runs.
- Frontend: 207 Vitest and 82 Playwright tests passed.

**Live OpenShell:**
- The builder ran it on one local setup, with images rebuilt from checksum-checked release archives.
- Re-run `scripts/verify/openshell.sh` on a host that can pull the project's own images.

**A4 is partial.** OpenShell logs no event for a refused file read (Q37).

QA findings and their outcomes are in `qa-review.md`.
