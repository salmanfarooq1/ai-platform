# Sprint 014: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 013's report. `check_skips` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** `local` mode answers a question with no external network: API, worker and Ollama on an internal-only network. Evidence: `evidence/ollama-offline.txt`.
- [ ] **A3.** The receipt of a `model.invoke` decision shows the model digest, and `scripts/verify/receipt.py` verifies it. Evidence: `evidence/receipt-digest.txt`.
- [ ] **A4.** A lock mismatch fails `scripts/models/check_lock.sh`, and the gateway denies the model with `model_digest_mismatch`. Evidence: `evidence/lock-mismatch.txt`.
- [ ] **A5.** The licence gate checks `models.lock` and fails on a fixture with a Llama-licensed model. Evidence: `evidence/licence-gate.txt`.
- [ ] **A6.** Measured tokens per second for the CPU profile (and the GPU profile if a GPU is present, else "not measured here"). Evidence: `evidence/tokens-per-second.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats --no-stream` for `ollama` with the 4B chat model and the embedding model loaded. Evidence: `evidence/memory.txt`.
