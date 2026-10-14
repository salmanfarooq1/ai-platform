# Sprint 027: Ask-your-data agent. Requirements

Vertical slice. Modules: M3 Agent Runtime (`api/agent/`, `sandbox_agent/`), using M4 through the `DataAccess` port and M1 for taint and receipts.

## Scope
1. **Agent tools and a mandatory sandbox.**
   - Four tools, each through `enforce()`: list metrics, describe dataset, query metric, and a guarded SQL fallback.
   - For data runs, the LangGraph agent runs inside the sandbox (Q34). OpenShell is mandatory for data agents. In-process is allowed only in tests.
2. **Session taint and the lethal-trifecta breaker.**
   - Any untrusted content taints the run.
   - A tainted run loses the tools that can send data out or write.
   - Markdown links and images are stripped from the output, or a proxy refuses them.
3. **Answer receipts** (record v2 extensions) carry:
   - the SQL hash, metric ids with their `group_by` and `filters`, one snapshot id and the result hash
   - the withheld columns and row-filter ids
   - the model digest
4. **Ask-data UI.** It shows the answer and the result table. A provenance panel shows the metric, the snapshot and the masks. A replay button re-runs the answer.
5. **Evals.**
   - A hand-verified set of 40+ questions on the reference company, scored by comparing result sets.
   - Abstention cases, and leakage tests (masked columns never change answers).
   - Three CI tiers:
     - PR: deterministic, with the fake model.
     - Nightly: the pinned local model at temperature 0.
     - Release: red team.
   - Nightly garak and PyRIT runs start here. Eval results are stored as signed records.

## Out of scope
- Document reading by agents (030).
- Policy-driven trifecta rules (038 moves them into OPA data) and guard models (038).
- Approval for over-limit queries (034). Over the limit is still a deny.

## Nav placement
Workspace > Ask.

## Questions this sprint closes
- **Q34:** for data runs, the LangGraph agent is packaged into the sandbox image. The thin retrieve-then-answer agent stays for knowledge-base runs.
- **Q40:** a proposed accuracy threshold for the nightly tier is recorded as a placeholder for the owner to agree, not as an agreed rule. Q40 in `QUESTIONS.md` is about cost display today, so the threshold is added as its second part (see the builder brief).
