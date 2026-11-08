# Sprint 013: Architect readiness decisions

> Superseded where it differs from `blueprint.md` and the 2026-11-02 re-plan (reranker removed, verifier is a policy option).

Preparation only. Implement after accepted 011/012 snapshots and finalize the full pack against that code. The dedicated Builder's read-only audit found the following mandatory corrections; no model weights or inference were used for this preparation.

## Govern the actual attempt

- Move retry and fallback selection above SDK adapters. Each physical completion, chat, embedding or optional reranker attempt resolves one immutable catalog target, obtains a recorded gateway allow, then passes that same resolution to a single-attempt provider. Never rebuild its model, endpoint, region or credentials from ambient overrides after enforcement.
- Cover synthesis retries (`api/services/llm.py`), reasoning/verifier attempts (`api/agent/graph.py`), embedding fallbacks (`adapters/litellm_embeddings.py`), search and worker ingestion batches. Submit-time job authorization cannot substitute for execution-time authority and per-batch decisions.
- Preserve optional cross-encoder reranking through an SDK-free port and an adapter, rather than leaving `CrossEncoder.predict` in `api/services/retriever.py`. Register its local source revision and artifact identity in the reviewed lock/catalog; authorize and record each prediction call before dispatch. Resolve verified local artifacts without request-time downloads or mutable model-name loading. Missing optional support or an unverifiable artifact must fail explicitly before inference; never silently discard a requested rerank or claim the feature is governed by an embedding allow. Include search, agent and MCP retrieval paths in the tests.
- Disable automatic retries at every underlying provider SDK. Verify physical request counts: the installed ChatLiteLLM wrapper uses `max_retries=1` as one total wrapper attempt, so similarly named knobs cannot be set blindly to zero.
- Catalog/identity failures produce recorded denials before provider I/O. Decision-write failure prevents transmission. Attempts bind tenant, request/run, resolved identity and route fingerprint. Keep authority no wider than the accepted boundary and current policy.
- Public `/health` and `/v1/health` use metadata readiness only, with zero inference. Preserve response schema and stale-vector reporting. Provider failures/logs must expose no prompt, credential or raw secret-bearing exception; remove the existing query snippet in the truncated-response log.

## Typed seams for the final blueprint

Frozen provider-independent values in `ports/`: `ModelIdentity` (alias, provider, source, local digest OR reviewed hosted model/version, processing scope/destinations, storage geography), `ModelRoute` (explicit immutable endpoint/transport parameters, credential reference, configuration fingerprint), and `ResolvedModel` (identity, route, use, provenance key, explicit price reference). `ModelCatalog.resolve(name, *, use)` and `probe()` are async and raise typed failures. Lock, hosted and fake implementations share contracts.

Define the missing env/file `SecretRef` and resolver before using them. Only adapters consume the resolved opaque secret. No plaintext request credential, implicit remote store, arbitrary endpoint override, secret in repr/log/record, or SDK import outside adapters.

Store the actual embedding digest/reviewed provider version in the existing TEXT provenance field and use it in retrieval/cache keys. Keep human alias separate for policy, pricing and display. Same alias with different digests must never share vectors or cached responses; unknown historical provenance stays stale until re-ingested.

## Local execution and profiles

Use the finally accepted 011 runtime. A named-tag check followed by invocation of the mutable alias is insufficient. Ollama's [0.34.4 resolver](https://raw.githubusercontent.com/ollama/ollama/v0.34.4/server/model_resolver.go) and [0.40.7 resolver](https://raw.githubusercontent.com/ollama/ollama/v0.40.7/server/model_resolver.go) differ in raw digest support. Spike exact digest invocation through completion, chat and embeddings before claiming it supported. Where unavailable, a verified read-only manifest/blob store and closed mutation API must remove the alias race.

The current completion `fallbacks` config has no production reader; introduce governed orchestration explicitly rather than claiming its old value already routed requests. Embedding fallback must preserve actual-vector identity and dimensions.

Preserve verifier-enabled defaults. The hosted profile without Ollama uses Gateway/Assurance, where no agent verifier is instantiated. Hosted Agents require a separate private local-only verifier target/runtime with no hosted fallback. Startup rejects a verifier configuration that cannot meet that constraint. CPU/GPU checks record only hardware actually exercised; no hardware or credential absence becomes a fake pass.

## Provider register and residency

Register all configured providers, including existing Gemini/Groq defaults, by service tier, model/configuration and retention mode. Unknown facts remain unknown and cannot satisfy a pin. Reject unpriced hosted targets and fallbacks in every MODE, including local. US-only inference price adjustments require an explicit price reference.

`allowed_regions` constrains verified possible processing destinations/scopes. Record endpoint location and storage geography separately; neither proves where inference runs. Canonical provider-scoped identifiers may name an explicit geography when exact region cannot be promised. Unknown scopes fail asserted pins; cross-region/global modes need every possible destination reviewed and contained.

- [Microsoft processing documentation](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy): processing scope differs from resource location and varies by deployment mode.
- [AWS cross-region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html): profiles route beyond source region. [Retention](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html) also depends on model/configuration.
- [Anthropic residency](https://platform.claude.com/docs/en/manage-claude/data-residency): inference geo and workspace storage geo are separate. Verify model support and pricing for an explicit geo; never silently omit it.
- [Gemini terms](https://ai.google.dev/gemini-api/terms) distinguish paid/unpaid data use. [Groq data handling](https://console.groq.com/docs/your-data) and [Anthropic retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) need equally specific register entries.

## Acceptance to add to the final pack

Denied fallback sends zero requests; each retry/batch and optional reranker prediction has its own recorded allow; recording failure sends nothing; alias/endpoint mutation cannot alter an authorized attempt; unknown price/residency denies; SDK retries cannot create hidden requests; same-alias/different-digest vectors remain isolated; both public health paths make zero inference calls; hosted Agents require local verification; signed v2 identity coexists with unchanged v1 verification. Add sentinel-content/credential tests for logs and errors, and retain existing assertions and fake-network guards.

Tiny manifest and licence downloads from the official registries established candidate identities only; the Builder must refresh/verify locks against the accepted runtime. No latency, memory, GPU or hosted-live result is claimed by this readiness review.
