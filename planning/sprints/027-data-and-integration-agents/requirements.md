# Sprint 027: Data and integration agents. Requirements

Agents pillar (M3), on Data and the Gateway. Our agents answer questions on client data in a sandbox, with a receipt for each answer. Integration agents help connect new sources: they read the schemas on both sides and suggest mappings. A human approves, and every call goes through the gateway like any other agent. The tag after this sprint (`v0.27.0`) is the freeze point.

Source: old 027, plus the agent part of old 030 and new scope (integration-data-connectors and gateway-proxy-and-agents research notes).

## Scope
1. **Agent tools and a mandatory sandbox.**
   - Tools, each through `enforce()`: list metrics, describe dataset, query metric, the guarded SQL fallback (025), and search documents (026 retriever with `AclFilter`).
   - For data runs, the LangGraph agent runs inside the OpenShell sandbox (Q34). In-process is allowed only in tests.
   - Every agent carries the 016 request contract and is in the registry.
2. **Session taint and the lethal-trifecta breaker.**
   - Untrusted content taints the run: document text (026), client source text fields marked untrusted, and tool outputs from outside.
   - A tainted run loses the tools that send data out or write.
   - The breaker reads its rules from 018 policy data, the same in both engines.
   - Markdown links and images are stripped from the output.
   - Malicious-PDF test: hidden instructions to leak data. Nothing leaves, and the tool calls are denied.
3. **Answer receipts** (record v2 extensions):
   - the SQL hash, metric ids with `group_by` and `filters`, the snapshot id or `as_of`, the result hash
   - withheld columns, row-filter ids, cited chunk ids, the model identity (013)
   - whether the answer can be replayed (021 rule)
4. **Ask-data UI.** It shows the answer and result table, a provenance panel (metric, snapshot, masks, citations), and a replay button. An over-limit query asks for approval (019).
5. **Integration agents.**
   - Triggered when a connection (021) or stream (022) is added, or on demand.
   - They read only schemas and a masked sample under a grant with purpose `integration`.
   - They suggest a mapping to the canonical model or the target contract (023), type fixes, keys, and quality issues. Valentine and bdikit (Magneto) produce candidates, and the model explains and ranks them.
   - The output is a proposal, never an applied change. A human approves it, and the approved mapping is versioned as generated dbt (022) or a contract change (023).
   - They run in the sandbox under the same taint rules. A template for them is registered for 028.
6. **Evals.**
   - A hand-verified set of 40+ questions on the reference company, scored by comparing result sets, plus abstention and leakage tests (masked columns never change answers).
   - A mapping set: known schema pairs with a gold mapping, scored on precision and recall.
   - Three CI tiers: PR (fake model), nightly (pinned local or hosted model at temperature 0), release (red team).
   - Nightly garak and PyRIT runs start here, in their own venv. Eval results are stored as signed records.

## Out of scope
- Auto-applying a mapping. Integration agents only suggest.
- External agents and agent templates in general (028). Long-term memory (028).
- Changed from old 027: guardrails, approvals and policy rules already exist (019, 018). Documents are searchable tools. Integration agents are new.

## Nav placement
- Workspace > Ask.
- Data > Connections: an "Integration suggestions" panel per connection, with approve and reject.

## Questions this sprint closes
- **Q34:** for data runs, the LangGraph agent is packaged into the sandbox image. The thin retrieve-then-answer agent stays for knowledge-base runs.
- **Q40 (second part):** the nightly accuracy threshold is recorded as a placeholder for the owner.
- Proposes the default for owner question Q-10 (are mappings always human-approved): yes.
