# Sprint 014: Local models. Requirements

Infrastructure, Kernel and M2. Local models by default, a model lock file and the model digest in evidence.

## Scope
1. Ollama runtime.
   - `ollama/ollama:0.34.4` in the `models` profile. The init job pulls the models in `models.lock`.
   - Settings: `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=1`, `num_ctx=8192`, keep-alive set.
2. Local defaults.
   - `local` mode chat uses `ollama/qwen3:4b-instruct-2507-q4_K_M`. Embeddings stay `ollama/nomic-embed-text` (768).
   - The local chat default today is a Gemini model, set in `core/settings.py` `_LLM_MODEL_DEFAULTS` (not in `config.py`). The fallback in `config.py` `LLM_CONFIG["fallbacks"]` for other modes is `ollama/llama3` (Llama licence). Change both.
   - Hosted providers stay optional adapters.
3. `models.lock`.
   - Name, digest, licence, source and size for each model.
   - A check script, `scripts/models/check_lock.sh`, compares pulled digests with the lock.
   - The licence gate covers models.
4. Model digest in evidence.
   - Every `model.invoke` decision record carries the model digest (a record v2 extension).
   - Receipts show it.
5. Profiles and verification.
   - CPU and GPU model profiles documented, with measured latency.
   - CI keeps the fake LLM. A nightly job runs a `qwen3:0.6b` smoke.
   - `scripts/verify/ollama.sh`. ADR-0014 (local by default, licence gate).

## Out of scope
- Guard models (038). Changing `public-preview` or `prod` chat defaults.
- Model cards and ML-BOM (043).

## Nav placement
No UI change. The receipt JSON carries the digest.

## Questions this sprint closes
- Q32: local models are priced at 0 in `MODEL_PRICING`. The hosted embedding prices stay open for an owner.
