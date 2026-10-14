# Sprint 014: Threat model
## Assets
- Model weights on disk and the model registry source.
- The decision chain (now naming model digests).
- Prompts and answers, which stay on the machine.

## Trust boundaries crossed
- The Ollama registry into the local model store (pull time only).
- The API and worker to Ollama on the compose network.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A pulled model differs from the reviewed one (registry change, local swap). | Tampering | `models.lock` digests; `check_lock.sh` after pull. | `test_models_lock.py::test_mismatch_fails`. |
| T2 | The digest drifts after startup, and calls go on with an unknown model. | Tampering | The catalog re-reads `/api/tags` on a miss; an unverified local model is denied `model_digest_mismatch`. | `test_model_digest_record.py::test_model_digest_mismatch_denies`. |
| T3 | A model under a non-OSI licence becomes a default. | Tampering (licence) | Licence gate reads `models.lock`; the `ollama/llama3` fallback is removed. | `test_settings_local_models.py::test_no_default_names_llama`; licence gate fixture. |
| T4 | A local mode run sends prompts to a hosted provider. | Information disclosure | Local defaults are `ollama/` only; the offline check runs with no route out. | `test_settings_local_models.py::test_local_defaults_need_no_network`; `evidence/ollama-offline.txt`. |
| T5 | A decision cannot prove which model answered. | Repudiation | `extensions.model` on every `model.invoke` row, inside the hash. | `test_model_digest_record.py::test_receipt_names_digest`. |
| T6 | Ollama is reached from the LAN and models are replaced. | Elevation of privilege | Port bound to `127.0.0.1` (012); `models` profile only. | `test_compose.py::test_no_port_on_all_interfaces`. |

## Abuse cases
- A user replaces `qwen3:4b-instruct-2507-q4_K_M` with a poisoned build under the same tag. The digest no longer matches, and calls are denied.
- A long prompt keeps a model loaded and starves others. `OLLAMA_NUM_PARALLEL=1`, `num_ctx=8192` and the existing token budget bound it.

## OWASP items in scope
- ASI04 (agentic supply chain): model digests and licences.
- LLM03 2026 (supply chain) and LLM04 2026 (data and model poisoning): lock file and digest check.
- LLM10 2026 (unbounded consumption): Ollama limits and the token budget.

## Residual risks
- The lock pins a digest, not the training data. Poisoned weights that were reviewed and locked still pass.
- The digest comes from the local Ollama. A compromised Ollama process could report a false digest.
