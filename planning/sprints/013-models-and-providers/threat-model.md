# Sprint 013: Threat model

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

STRIDE over model catalogs, admission, attempts, policy, secrets, local runtime and signed evidence.

| # | Threat | STRIDE | Control | Test |
|---|---|---|---|---|
| T1 | An attempt or fallback runs without its own allow. | Elevation of privilege | Admission precedes inference; every physical attempt has its own recorded allow. | `test_model_caller.py::test_admission_precedes_all_model_io`, `::test_fallback_needs_its_own_allow` |
| T2 | An SDK retries and sends hidden requests. | Elevation of privilege | SDK retries are disabled on LiteLLM, OpenAI, Azure and Bedrock paths. | `test_sdk_retries.py::test_one_request_per_attempt[...]` |
| T3 | Ollama runs a retagged model after authorization. | Tampering | Calls use the immutable digest reference; the lock is checked and the serving store is read-only. | `test_lock_catalog.py::test_route_uses_digest_reference`; live digest check |
| T4 | Settings or a request changes the route after enforcement. | Tampering | A frozen resolved route is passed unchanged to the adapter. | `test_model_caller.py::test_route_is_the_resolved_one` |
| T5 | A hosted model processes data outside the allowed region. | Information disclosure | Register scopes and `DEPLOY_REGION` are checked against `allowed_regions`; unknown scope denies. | `test_region_pin.py`; `test_local_region_and_bedrock_minimum` |
| T6 | A provider uses data in a way the tenant disallows. | Information disclosure | `allowed_data_use` denies providers marked training or unknown. | `test_data_use.py::test_training_provider_denied` |
| T7 | Secret material leaks into logs, errors, records or receipts. | Information disclosure | Secrets are opaque outside adapters; sentinel checks cover records, receipts, errors and logs. | `test_secrets.py::test_sentinel_never_leaks`; `test_model_records.py::test_secret_sentinel_not_in_record_receipt_or_error` |
| T8 | A file secret is replaced or read by another user. | Tampering | Resolver requires a regular, owned file with no group/world permissions and rejects symlinks. | `test_secrets.py::test_file_ref_rules` |
| T9 | A decision write fails but inference still runs. | Repudiation | The caller sends only after a recorded allow. | `test_model_caller.py::test_unrecorded_attempt_is_not_sent` |
| T10 | Health probes cause unrecorded inference. | Elevation of privilege | Health uses catalog metadata only. | `test_health.py::test_health_makes_no_inference` |
| T11 | Vectors or cached answers from different model identities mix. | Tampering | Provenance and cache keys include digest or provider model id. | `test_vector_identity.py` |
| T12 | The verifier bypasses region or data-use policy. | Information disclosure | The verifier uses the same admission and policy path; a tenant can require it to be local. | `test_verifier_policy.py::test_verifier_uses_same_policy_checks` |
| T13 | A configured provider lacks reviewed data-use terms. | Information disclosure | Every configured alias needs a register entry; unknown terms cannot satisfy a data-use pin. | `test_provider_register.py::test_configured_provider_needs_entry`; `test_data_use.py::test_training_provider_denied` |
| T14 | A model endpoint host is not in the application allowlist. | Information disclosure | `MODEL_ALLOWED_HOSTS` checks the resolved hosted endpoint. It is an application-level allowlist; network egress control is in Sprint 016. | `test_model_caller.py::test_endpoint_host_must_be_allowed` |
| T15 | A model-call input bypasses guardrails or is stored in evidence. | Information disclosure | Existing input guardrails scan caller-supplied model input; platform-built text and ingest batches are `skipped` and recorded as such; records contain only hashes and matched rule ids. Indirect injection through retrieved content is handled by output checks in 019 and taint in 027. | `test_model_caller.py::test_input_guardrail_runs_before_request` |
| T16 | An open or overloaded route still sends a provider request. | Denial of service | Route breaker and tenant concurrency lease deny before dispatch. | `test_model_caller.py::test_open_breaker_denies_without_request`; `test_model_caller_limits.py::test_tenant_concurrency_cap_denies_without_request` |
| T17 | A receipt omits or alters the stage history. | Repudiation | Closed `stages` schema is included in the signed record; offline verifier checks and prints it. | `test_stages_extension.py::test_every_stage_is_recorded_in_order`; `test_receipt_verifier.py::test_model_and_stages_extensions_verify` |
