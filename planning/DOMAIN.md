# Domain

## What the platform does
It runs **governed agents on business data**. Agents answer questions and do tasks over a company's documents and data. Every call to a model, tool or data source goes through one control point that checks who is asking, what they may do, and what it costs, and records what happened.

## Users
- **End user:** asks questions, uploads documents, reads cited answers.
- **Operator:** manages tenants, knowledge bases, policies and budgets, and reviews audit records and costs.
- **Agent or client:** an MCP client or an A2A agent calling the platform through the gateway.
- **Developer:** builds use cases on top of the platform.

## Use cases built on top (planned)
- An ask-your-data agent: a semantic layer first, text-to-SQL as a fallback, with accuracy evals.
- A document agent: turns forms and invoices into structured data, with a review queue.
- More will be added in `ROADMAP.md` as they are agreed.

## Vocabulary
| Term | Meaning |
|---|---|
| Tenant | An isolated customer or organisation. Every row belongs to exactly one tenant. |
| Principal | The authenticated caller (user, service or agent), taken from a verified token. |
| Knowledge base (KB) | A named collection of documents owned by a tenant. Today this is called a "namespace". |
| Collection | The UI word for a knowledge base. |
| ExecutionBoundary | The fixed set of permissions for one request: which tools, KBs, models and budget are allowed. |
| `enforce()` | The single gateway entry point. It authenticates, resolves the tenant, applies policy, guardrails and budget, routes, and audits. |
| Receipt | The audit record for each request: policy version, model route and content hashes. It never holds raw content. |
| Mode | `local`, `public-preview` or `prod`. It selects the external services used. |
| Walking skeleton | The thinnest correct version of a feature, with what was deferred named and a seam left for it. |
| Module | A registered capability with its own optional routes, transports or job handlers. |
| Pillar | One of the platform's organizing areas: Platform, Gateway, Data or Agents. |
| Edition | A named set of enabled modules, such as Gateway, Assurance, Agents, Data or Full. |
| Deploy shape | The tenant-count mode selected for an installation: `single_tenant` or `multi_tenant`. |
| Module stage | The gateway check after principal authorization that denies actions belonging to disabled modules. |
| Record version | The version of the canonical decision fields used to hash and verify a decision record. |
| Extension | A registered, schema-checked value included in a version 2 decision record's hash. |
| Evidence core | The package that writes decision records, maintains their hash chain and builds receipts. |
