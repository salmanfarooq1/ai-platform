# Sprint 013: Models and providers. Requirements

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Gateway pillar, Kernel and evidence-core fields, including Gateway edition with M2 off. The client chooses the model: local or hosted, both pinned, both named in the record.

The 012 worktree is the implementation baseline.

## Scope
1. **Ollama runtime (local).**
   - Use the verified Ollama runtime selected in 011 in the `models` profile, with digest/hash-pinned image inputs. The init job pulls and verifies the exact models in `models.lock`; runtime invocation must bind their immutable identity.
   - Settings: `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=1`, `num_ctx=8192`, keep-alive set.
2. **Local defaults.**
   - `local` mode chat uses `ollama/qwen3:4b-instruct-2507-q4_K_M`. Embeddings stay `ollama/nomic-embed-text` (768, v1.5).
   - `VERIFIER_MODEL` defaults to the local chat model but may be hosted unless policy sets `verifier_must_be_local`.
   - Set `_LLM_MODEL_DEFAULTS["local"]` in `core/settings.py` to the chat model above. Set `LLM_CONFIG["fallbacks"]` in `config.py` to `ollama/qwen3:1.7b`.
3. **`models.lock`.**
   - Name, digest, licence, source, size and use for each local model. `scripts/models/check_lock.sh` compares pulled digests with the lock.
   - The licence gate covers models (OSI allowlist).
4. **Hosted providers as an equal option.**
   - Azure OpenAI, Bedrock, Anthropic and any OpenAI-compatible endpoint (vLLM) through the existing LiteLLM adapter. No new SDK outside `adapters/`.
   - Credentials come by reference from the secret store. `MODEL_ALLOWED_HOSTS` is an application-level allowlist. Network egress control for the API container is in Sprint 016.
   - A hosted model with no price entry refuses to start (existing rule). Prices for hosted embeddings stay an owner input.
   - Guard and judge calls stay local. A hosted guard arrives only through the 019 guard-provider port.
   - `ModelCaller` owns retries and fallback selection above SDK adapters. Authorize and record each physical attempt, including each embedding batch in ingestion workers. Bind the resolved catalog identity to that attempt. A primary-model allow never grants another model, provider or region. Disable hidden SDK retries. Public health uses metadata readiness only and makes no inference call. The verifier uses its own configured model and the same admission, region and data-use checks as other models.
   - Define the currently missing typed env/file secret-reference resolver; no remote secret service is assumed. Plaintext request credentials and secret values in records/logs are forbidden.
5. **Provider register.**
   - One reviewed file in the repo (`providers.register.toml`, name recorded in `conventions.md`). Each provider has data-use terms (trains on data or not, retention), allowed regions and a source link.
   - CI fails when a configured provider has no register entry.
6. **Region pin and model identity in records.**
   - The policy document gains `allowed_regions`. A hosted call outside the pin is denied with `region_not_allowed` (stage `policy`).
   - Every model decision carries `extensions.model`: `{name, provider, source, digest | provider_model_id, processing_scope, route, phase}`. Receipts show it. Every decision also carries the ordered `extensions.stages` list.
   - A local model whose digest does not match the lock is denied with `model_digest_mismatch`.
   - A `ModelCatalog` port (`ports/models.py`) with a Lock adapter and a hosted adapter. Contract suite on both and a fake.
7. **CPU profile and verification.**
   - Document the CPU profile with measured latency and memory. Do not document GPU or hosted profiles.
   - CI keeps the fake LLM. A live Ollama test checks digest-reference resolution when the real service is available and fails if resolution stops working.
   - `scripts/verify/ollama.sh` on an `internal: true` network, and a hosted smoke that needs keys and is skipped without them.
   - ADR-0014 (revised): local or hosted, the provider register, the model lock and the licence gate.

8. **Admission and data use.**
   - Before inference, admit every model alias the request will need. Search admits chat and embeddings; agents admit reasoning and verifier; MCP retrieval admits the models it uses. Admission records use `extensions.model.phase = "admission"`; they grant no run-time authority. A denied admission stops before any model request.
   - Every physical attempt has its own allow with `phase = "attempt"`. A chat admission deny makes zero chat and embedding requests.
   - Policy gains `allowed_data_use`, default `"*"`. A provider marked as training on data or unknown is denied `data_use_not_allowed` when the policy sets a list.
   - `local` is not a region. `DEPLOY_REGION` names the deployment's region. A region pin with no `DEPLOY_REGION` refuses startup. Bedrock scope validation must not accept a configured scope narrower than its model id permits.

9. **Limits and evidence.**
   - A breaker is keyed by route fingerprint. It opens after 5 consecutive provider failures, becomes half-open after 30 seconds and permits one trial. An open route is denied `model_breaker_open` before I/O.
   - A Valkey lease caps in-flight attempts per tenant at `MODEL_MAX_CONCURRENT_PER_TENANT` (default 8). Over-limit attempts are denied `model_concurrency_limit` before I/O.
   - Every decision has a signed v2 `stages` extension. It lists each stage in order with status, reason and duration. Stages after a deny are `not_reached`; inapplicable stages are `skipped`.
   - The input guardrail scans caller-supplied model input (the user's question or messages, including the query text sent for embedding) before provider I/O. Platform-built parts (system prompt, retrieved context) and ingest embedding batches are not scanned and show as `skipped`. The tenant query-length cap does not apply to whole model prompts. It fails closed. Records contain hashes and matched rule ids, never prompt text.
   - A tiny benchmark test keeps `scripts/bench/decision_path.py` runnable. The Architect captures the live benchmark in `evidence/decision-path-bench.txt`; Sprint 013 sets no performance target.

## Out of scope
- Guard models and output guardrails (019). Changing `public-preview` or `prod` chat defaults.
- Model cards and ML-BOM (030).
- Choosing a hosted provider for a client. The register only records what is known.
- Reranking is removed. The `rerank` request field stays for one release, is deprecated in OpenAPI and ignored. It does not affect cache keys. Remove the cross-encoder dependency, port, adapter, model-lock entry and local-hf provider. Reranking returns as a governed port when a client needs it.
- GPU and hosted profile documentation and a nightly model workflow.

## Nav placement
No new page. Evidence > Decisions shows the model block and ordered stage list. Receipt JSON and Trust > Verify show signed model and stage fields.

## Questions this sprint closes
- Q32: local models are priced at 0 in `MODEL_PRICING`. The hosted embedding prices stay open for the owner.
