# Sprint 033: Acceptance
- [ ] **A1.** All checks pass. The test delta is stated against Sprint 032's report. `check_skips` passes with the allowlist, with no new entries. Evidence: `evidence/checks.txt`.
- [ ] **A2.** A stateless MCP 2026-07-28 client lists and calls tools on `POST /v1/mcp`. The legacy SSE transport is off unless the flag is set. Evidence: `evidence/stateless-client.txt`.
- [ ] **A3.** A header that disagrees with the body is rejected with `-32020`, and a deny row `mcp_header_mismatch` is written. Evidence: `evidence/header-mismatch.txt`.
- [ ] **A4.** Token passthrough is impossible: the downstream peer never sees the caller's token. A JWT for another audience is refused. Evidence: `evidence/no-passthrough.txt`.
- [ ] **A5.** A changed tool description is hidden and its call is denied `tool_definition_changed` until an admin approves it again. Evidence: `evidence/tool-pins.txt`.
- [ ] **A6.** An unsigned or wrongly signed manifest is refused. An approved server's tools work through the registry, with `traceparent` in the records. Evidence: `evidence/registry.txt` and the Playwright run.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** Not applicable: no new compose service.
