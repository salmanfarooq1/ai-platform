# Sprint 004: QA and code review

The QA agent returned this as text, and the Architect saved it. The evidence is in `evidence/qa-*.txt`.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass | ruff and mypy (79 files) clean, DDL guard OK, 395 unit tests |
| A2 | pass | 272 int+e2e, 0 skipped. "Assertions unchanged" can't be proven from git, because the tree is uncommitted |
| A3 | pass | scenarios 1–9 mapped. The e2e tests assert fake call counts and decision rows |
| A4 | pass | middleware gone. 25 import-lint tests |
| A5 | pass | live: allow 200, KB deny 403, model deny 403, guardrail 400. 0 query-text hits in pg_dump |
| A6 | pass | 6 stages parametrized |
| A7 | pass | 3 × 300 examples |
| A8 | pass | 0004 → 0005 on data, digests identical |
| A9 | partly verified | docs present, not reviewed line by line |

## Bypass hunt
The agent and route paths are fully gated. In a live comparison, every fake LLM and embedding call had an allow row before it.

## Findings
**High:** none.

**Medium**
1. MCP gates only `kb.read`, so the tool and model allowlists and `max_tokens` are ignored (`api/mcp/tools.py`, `resources.py`).
2. A failed decision write on an allow lets the call through with no row (`gateway/record.py:42`).
3. `/v1/config` lists KBs the policy denies (`api/routers/config.py:29`).
4. Feedback, quality-report and analytics have no `enforce()` (`feedback.py:39,70`, `analytics.py:27`).

**Low**
1. The import-lint checks direct imports only, and `graph.py` isn't guarded. There's no structural check that tools call the gate.
2. Scope denials leave no decision row.
3. The completion `max_tokens` isn't counted against `max_tokens_per_request`.
4. The verifier still runs after a halt.
5. `tool_calls_made` counts denied calls.
6. The health probe is ungated (accepted).
7. A tenant with a KB allowlist gets 403 rather than 404 for unknown KBs.
8. Diff isolation (commit the earlier sprints first).

## Not verified
- The image build.
- The byte-identical Sprint 003 tests.
- A concurrent tool-call race on `ctx.tool_calls`.

## Architect disposition
- **Sent back to the Builder:** M1–M4 and L1–L4, plus L7 as an ADR note.
- **Accepted:** L5 (cosmetic) and L6 (exempt by AGENTS.md).
- **Process:** L8.

## QA re-check of the follow-ups
M1–M4 and L2–L4 are fixed and tested. L1 is fixed, with the weak spot N2 below. The bypass hunt found no ungated LLM, embedding or data call except N1. No failed decision write can let an allow through.

**Medium**
- **N1:** `multi_namespace_search` with explicit namespaces skipped its own `tool.call` check. **Fixed** by the Architect in `api/mcp/tools.py`, with a new e2e test. Without the fix, the test fails.
- **N4:** ADR-0006 said no model call runs after a halt, but one gated synthesis call builds the partial answer. This is by design. **Fixed:** the ADR wording is corrected.

**Low (accepted, recorded in `planning/RISKS.md`)**
- **N2:** the gate-call lint checks that a gate call exists, not which actions it passes.
- **N3:** MCP scope denials leave no decision row.
- **N5:** parallel tool calls can overshoot `max_tool_calls`.
- **N6:** a denied `decision_unrecorded` call still used up its rate and budget counters.
- **N7:** ingest embedding isn't bounded by `max_tokens_per_request`.
- **N8:** some error bodies include exception text. Most of this predates Sprint 004.
- **N9:** the public health probe calls the embedding provider (L6).

**Sign-off:** Sprint 004 is done. The Architect re-ran the full suite: 709 passed, 0 skipped.
