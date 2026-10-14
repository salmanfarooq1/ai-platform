# Sprint 013: Models and providers. Requirements

Gateway pillar, Kernel and M2 evidence fields. The client chooses the model: local or hosted, both pinned, both named in the record.

Source: old 014, plus new scope (owner direction of 2026-10-11, `review.md`).

## Scope
1. **Ollama runtime (local).**
   - `ollama/ollama:0.34.4` in the `models` profile, pinned by digest. The init job pulls the models in `models.lock`.
   - Settings: `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=1`, `num_ctx=8192`, keep-alive set.
2. **Local defaults.**
   - `local` mode chat uses `ollama/qwen3:4b-instruct-2507-q4_K_M`. Embeddings stay `ollama/nomic-embed-text` (768, v1.5).
   - Change two places: `_LLM_MODEL_DEFAULTS` in `core/settings.py` (a Gemini model today) and `LLM_CONFIG["fallbacks"]` in `config.py` (`ollama/llama3`, Llama licence). The fallback becomes `ollama/qwen3:1.7b`.
3. **`models.lock`.**
   - Name, digest, licence, source, size and use for each local model. `scripts/models/check_lock.sh` compares pulled digests with the lock.
   - The licence gate covers models (OSI allowlist).
4. **Hosted providers as an equal option.**
   - Azure OpenAI, Bedrock, Anthropic and any OpenAI-compatible endpoint (vLLM) through the existing LiteLLM adapter. No new SDK outside `adapters/`.
   - Credentials come by reference from the secret store. Egress is allowed only to the provider hosts named in settings.
   - A hosted model with no price entry refuses to start (existing rule). Prices for hosted embeddings stay an owner input.
   - Guard and judge calls stay local. A hosted guard arrives only through the 019 guard-provider port.
5. **Provider register.**
   - One reviewed file in the repo (`providers.register.toml`, name recorded in `conventions.md`). Each provider has data-use terms (trains on data or not, retention), allowed regions and a source link.
   - CI fails when a configured provider has no register entry.
6. **Region pin and model identity in records.**
   - The policy document gains `allowed_regions`. A hosted call outside the pin is denied with `region_not_allowed` (stage `policy`).
   - Every `model.invoke` record carries `extensions.model`: `{name, digest or provider_model_id, source, provider, region}`. Receipts show it.
   - A local model whose digest does not match the lock is denied with `model_digest_mismatch`.
   - A `ModelCatalog` port (`ports/models.py`) with a Lock adapter and a hosted adapter. Contract suite on both and a fake.
7. **Profiles and verification.**
   - Three profiles documented, with measured latency and memory: CPU, GPU and hosted (no Ollama).
   - CI keeps the fake LLM. A nightly job runs a `qwen3:0.6b` smoke.
   - `scripts/verify/ollama.sh` on an `internal: true` network, and a hosted smoke that needs keys and is skipped without them.
   - ADR-0014 (revised): local or hosted, the provider register and the licence gate.

## Out of scope
- Guard models (019). Changing `public-preview` or `prod` chat defaults.
- Model cards and ML-BOM (030).
- Choosing a hosted provider for a client. The register only records what is known.
- Dropped from old 014: "hosted providers stay optional adapters". They are now equal, with a register and a region pin.

## Nav placement
No new page. The receipt JSON and Evidence > Decisions show provider, region and digest.

## Questions this sprint closes
- Q32: local models are priced at 0 in `MODEL_PRICING`. The hosted embedding prices stay open for the owner.
