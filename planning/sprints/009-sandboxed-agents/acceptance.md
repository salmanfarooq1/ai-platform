# Sprint 009: Acceptance
- [ ] **A1.** All checks pass with 0 skipped. The OpenShell adapter passes the AgentRuntime contract suite, against the real sandbox or the recorded fake (say which).
- [ ] **A2.** The agent completes an authorized task in the sandbox.
- [ ] **A3.** A direct call to a model provider from inside the sandbox fails, and a network-deny event is recorded.
- [ ] **A4.** Reading a file outside the work directory fails, and an event is recorded.
- [ ] **A5.** An unauthorized tool argument gets a gateway deny row with reason `tool_argument_not_allowed`.
- [ ] **A6.** Sandbox events join `gateway_decisions` by `execution_id` in the runs API and on the Agent runs page (Playwright).
- [ ] **A7.** A2-A5 are run live on a Linux host via `scripts/verify/openshell.sh`, or marked "not verified here" with the runbook.
