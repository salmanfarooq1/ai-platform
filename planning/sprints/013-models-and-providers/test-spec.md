# Sprint 013: Test specification

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

The Architect wrote these tests before the code. Builders write each test with exactly this name and expected result. A builder may add tests. A builder never changes, skips or loosens a listed test. If a listed test seems wrong, write it under "Spec questions" in `build-log.md` and leave it as specified.

Tiers: **U** unit, **C** contract (runs on every implementation and the fake), **I** integration (real Postgres and Valkey), **L** live model (real Ollama; Architect-run when the service is available), **V** Vitest, **P** Playwright.

Shared test doubles (in `tests/fakes.py`):
- `RecordingProvider`: an in-process stand-in for a provider that counts physical requests per model id and can fail the next N requests with a given error.
- `StubOpenAIServer` (`tests/stub_llm_server.py`): a local HTTP server on a free port that speaks the OpenAI chat, completion and embedding routes and the Ollama `/api/chat`, `/api/generate`, `/api/embed` routes, counts requests, and can return 429 or 500 for the next N requests. Used for SDK retry counts.
- `FakeCatalog`: resolves from an in-memory table; can raise each typed failure.

## Baseline
Taken from Sprint 012's final report when it is accepted.

## WP1: Contracts and secrets
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 1.1 | `tests/unit/test_model_types.py::test_identity_route_resolved_are_frozen` | U | Assigning to any field of `ModelIdentity`, `ModelRoute` or `ResolvedModel` raises `FrozenInstanceError`; `ModelRoute.params` rejects mutation. | A2, T4 |
| 1.2 | `tests/unit/test_model_types.py::test_identity_needs_digest_or_provider_model_id` | U | A local identity without a `sha256:<64 hex>` digest raises `ValueError`. A hosted identity without `provider_model_id` raises `ValueError`. Both set raises. | A4 |
| 1.3 | `tests/unit/test_model_types.py::test_extension_matches_registered_schema` | U | `identity.as_extension(phase)` for local and hosted identities passes the closed model schema for `admission` and `attempt`. Adding any other key fails. | A2, A13 |
| 1.4 | `tests/unit/test_model_types.py::test_fingerprint_changes_with_any_route_field` | U | Changing endpoint, credential ref name, any param or the identity changes `ModelRoute.fingerprint`. | A2, T4 |
| 1.5 | `tests/unit/test_secrets.py::test_ref_syntax` | U | `env:NAME` and `file:/abs/path` parse. `NAME`, `env:`, `file:rel/path`, `vault:x` and `http://x` raise `ValueError`. | A8 |
| 1.6 | `tests/unit/test_secrets.py::test_file_ref_rules` | U | A 0600 regular file owned by the user resolves. A symlink, a 0640 file, a 0604 file and a directory are refused with `SecretRefError`. | A9, T7 |
| 1.7 | `tests/unit/test_secrets.py::test_sentinel_never_leaks` | U | With sentinel value `sk-SENTINEL-7f3a`, `repr`, `str`, `f"{secret}"`, `logging` of the object, and the message of a resolver error never contain the sentinel. | A9, T6 |
| 1.8 | `tests/contracts/test_model_catalog_contract.py` | C | Runs on `FakeCatalog`, `LockCatalog` (with a temp lock and a stub Ollama `/api/tags`) and `RegisterCatalog` (with a temp register): resolve a known alias for an allowed use returns a `ResolvedModel` whose `use` equals the request; an unknown alias raises `UnknownModel`; a use not in the entry raises `UnknownModel`; `probe()` makes zero inference requests. | A3, A10 |

## WP2: Lock and register
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 2.1 | `tests/unit/test_models_lock.py::test_lock_is_valid` | U | `models.lock` parses; every entry has the required fields; digests match `^sha256:[0-9a-f]{64}$`; uses are valid `ModelUse` values. | A4 |
| 2.2 | `tests/unit/test_models_lock.py::test_lock_licences_are_osi` | U | Every `licence` is on the OSI allowlist used by the 011 licence gate. A temp lock with `licence = "LLAMA-3"` fails the gate function. | A8 |
| 2.3 | `tests/unit/test_models_lock.py::test_every_local_default_is_locked` | U | The local chat default, completion fallback, embedding model and local verifier default have lock entries with matching uses. | A14 |
| 2.4 | `tests/unit/test_provider_register.py::test_register_is_valid` | U | Every provider has `name`, `trains_on_data`, `retention`, `processing_scopes` (each with a description), `sources` (https URLs) and `reviewed` (ISO date). | A8 |
| 2.5 | `tests/unit/test_provider_register.py::test_configured_provider_needs_entry` | U | For each MODE, every provider prefix of configured chat, embedding, fallback and verifier aliases has a register entry. A temp setting `LLM_MODEL=mistral/x` fails with a message naming `mistral`. | A8, A20 |
| 2.6 | `tests/unit/test_check_lock_script.py::test_check_lock_detects_mismatch` | U | `scripts/models/check_lock.sh` against a stub `/api/tags` that matches the lock exits 0; with one digest changed it exits 1 and names the alias; with one model missing it exits 1. | A4 |

## WP3: Catalog adapters
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 3.1 | `tests/unit/test_lock_catalog.py::test_route_uses_digest_reference` | U | Resolving the chat alias gives route model `ollama_chat/sha256:<digest>`; completion gives `ollama/sha256:<digest>`; embedding gives `ollama/sha256:<digest>`. The alias stays in `identity.alias`. | A4, T3 |
| 3.2 | `tests/unit/test_lock_catalog.py::test_pulled_digest_mismatch_raises` | U | Stub `/api/tags` reports a different digest for the alias; `resolve` raises `ModelDigestMismatch`. Missing from tags raises `UnknownModel`. | A4 |
| 3.3 | `tests/unit/test_register_catalog.py::test_unpriced_hosted_model_raises_in_every_mode` | U | For `local`, `public-preview` and `prod`, a hosted alias with no `MODEL_PRICING` entry raises `UnpricedModel`. | A3 |
| 3.4 | `tests/unit/test_register_catalog.py::test_unknown_scope_raises` | U | A hosted provider whose configured deployment scope is not in the register raises `ResidencyUnknown`. | A6, T5 |
| 3.5 | `tests/unit/test_register_catalog.py::test_credential_comes_from_ref` | U | The route's `credential` is the configured `SecretRef`; no field holds the secret value. | A8 |

## WP4: Gateway, policy and records
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 4.1 | `tests/unit/test_reason_catalogue.py` (existing) | U | Passes with all new model, data-use, breaker, concurrency and verifier reasons, each with its stage and `policy_field`. | A7, A12, A16, A20 |
| 4.2 | `tests/unit/test_region_pin.py::test_scope_outside_pin_is_denied` | U | Policy `allowed_regions=["eu"]`; attempt with scope `azure:us`: deny `region_not_allowed`, stage `policy`. Scope `azure:eu-data-zone` mapped to region `eu` in the register: allow. | A6 |
| 4.3 | `tests/unit/test_region_pin.py::test_unknown_scope_never_matches` | U | Scope `unknown` with pin `["eu"]`: deny. With pin `"*"`: deny `residency_unknown` from the model stage (unknown is never allowed for hosted). | A6, T5 |
| 4.4 | `tests/unit/test_region_pin.py::test_local_scope` | U | With `DEPLOY_REGION="eu"`, a local attempt passes pin `["eu"]`, denies pin `["us"]`, and passes pin `"*"`. | A6 |
| 4.5 | `tests/integration/test_model_records.py::test_model_invoke_record_carries_extension` | I | One real search through the API with the fake provider: every `model.invoke` row has `record_version=2` and `extensions.model` equal to the resolved identity plus route fingerprint; the receipt's `canonical` contains it. | A2, A12 |
| 4.6 | `tests/integration/test_model_records.py::test_catalog_failure_is_recorded_before_io` | I | For each typed failure from `FakeCatalog`, the API call is denied with the matching reason, one deny row exists, and `RecordingProvider` counted zero requests. | A3 |
| 4.7 | `tests/unit/test_stages_extension.py::test_every_stage_is_recorded_in_order` | U | Every decision has the registered closed `stages` extension; applied stages pass in order, inapplicable stages are `skipped`, and stages after a deny are `not_reached`. | A13, A20 |
| 4.8 | `tests/unit/test_model_stage_order.py::test_boundary_deny_precedes_residency` | U | A caller without the required scope gets a boundary deny before the model stage can return `residency_unknown`. | A6, A20 |
| 4.9 | `tests/unit/test_data_use.py::test_training_provider_denied` | U | With `allowed_data_use=["no_training"]`, a provider marked `yes` or `unknown` denies `data_use_not_allowed` at policy. | A7 |
| 4.10 | `tests/unit/test_region_pin.py::test_local_region_and_bedrock_minimum` | U | A local route uses `DEPLOY_REGION`; a listed pin with no deployment region refuses startup. A Bedrock model id prefix rejects a narrower configured scope. | A6 |
| 4.11 | `tests/integration/test_receipt_verifier.py::test_model_and_stages_extensions_verify` | I | `scripts/verify/receipt.py` verifies a receipt with `extensions.model` and `extensions.stages`, prints the stage list, and verifies a v1 receipt unchanged. | A13 |
| 4.12 | `tests/integration/test_model_records.py::test_secret_sentinel_not_in_record_receipt_or_error` | I | A sentinel in provider settings is absent from decision rows, receipts, API error bodies and captured logs. | A9 |

## WP5: Model caller and single attempts
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 5.1 | `tests/unit/test_model_caller.py::test_each_retry_has_its_own_decision` | U | Provider fails twice with a rate-limit error, then answers. `complete` makes 3 requests and 3 `model.invoke` allows, in order, each before its request. | A2, T1 |
| 5.2 | `tests/unit/test_model_caller.py::test_fallback_needs_its_own_allow` | U | Primary fails with a non-retryable error; policy denies the fallback alias. Result is a deny; the fallback got zero requests; there are 2 decisions (allow primary, deny fallback). | A3, T1 |
| 5.3 | `tests/unit/test_model_caller.py::test_unrecorded_attempt_is_not_sent` | U | Decision sink raises on write. Zero requests; the error surfaces as `decision_unrecorded`. | A3, T8 |
| 5.4 | `tests/unit/test_model_caller.py::test_route_is_the_resolved_one` | U | After resolution, changing settings, env and the catalog table does not change the model, endpoint or credential ref the adapter receives for that attempt. | A2, T4 |
| 5.5 | `tests/unit/test_model_caller.py::test_endpoint_host_must_be_allowed` | U | A resolved hosted route whose host is not in `MODEL_ALLOWED_HOSTS` is denied before I/O. `MODEL_ALLOWED_HOSTS` is an application-level allowlist; it is not network egress control. | A3, T14 |
| 5.6 | `tests/integration/test_sdk_retries.py::test_one_request_per_attempt[completion]` | I | Against a local stub that fails once with 500, `LitellmLLM` makes exactly 1 HTTP request. | A5, T2 |
| 5.7 | `tests/integration/test_sdk_retries.py::test_one_request_per_attempt[chat]` | I | Against a local stub that fails once with 500, `LitellmChat` makes exactly 1 HTTP request. | A5, T2 |
| 5.8 | `tests/integration/test_sdk_retries.py::test_provider_routes_make_one_request[openai|azure|anthropic|bedrock|ollama]` | I | Each route uses a local stub that fails once with 500; OpenAI, Azure, Anthropic, Bedrock stub and Ollama each make exactly 1 HTTP request. | A5, T2 |
| 5.9 | `tests/integration/test_sdk_retries.py::test_one_request_per_attempt[embedding]` | I | Against a local stub that fails once with 500, `LitellmEmbeddings` makes exactly 1 HTTP request. | A5, T2 |
| 5.10 | `tests/e2e/test_attempts_e2e.py::test_agent_reasoning_and_verifier_each_recorded` | I | An agent run with the fake chat model that reasons twice and verifies once writes admission rows for both aliases and 3 `model.invoke` attempt rows; the verifier row names its configured identity. | A2, A12 |
| 5.11 | `tests/unit/test_model_caller.py::test_admission_precedes_all_model_io` | U | A denied chat admission for search records the admission deny and makes zero chat and embedding requests. | A2, A3 |
| 5.12 | `tests/unit/test_model_caller.py::test_open_breaker_denies_without_request` | U | An open route denies `model_breaker_open` at stage `model`; the provider count stays zero and fallback selection continues. | A16 |
| 5.13 | `tests/integration/test_model_caller_limits.py::test_tenant_concurrency_cap_denies_without_request` | I | With the tenant at its configured in-flight cap, the next attempt denies `model_concurrency_limit` at stage `rate`; provider count stays zero. | A16 |
| 5.14 | `tests/unit/test_model_caller.py::test_input_guardrail_runs_before_request` | U | A blocked user question or chat message denies before provider I/O, including its query embedding; the decision stores its input hash and matched rule ids, not the text. | A19 |
| 5.15 | `tests/unit/test_model_caller.py::test_input_guardrail_skips_platform_text` | U | A synthesis whose retrieved context exceeds `max_query_length` and contains a blocked pattern is allowed; an ingest embedding batch shows the guardrail stage as `skipped`. | A19 |

## WP6: Embeddings, ingest and vector identity
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 6.1 | `tests/unit/test_model_caller.py::test_embedding_fallback_records_each_target` | U | Primary embedding fails, fallback answers. 2 decisions, 2 requests; `Embeddings.model` is the fallback identity; the dimension check still applies. | A2 |
| 6.2 | `tests/integration/test_ingest_attempts.py::test_each_batch_is_authorized_at_run_time` | I | Ingest a document that makes 3 batches (batch size from settings). The job writes 3 `model.invoke` rows with the job's request id; a policy change that removes the embedding model between submit and run makes the job fail with a recorded deny and zero embedding requests. | A2 |
| 6.3 | `tests/integration/test_vector_identity.py::test_two_digests_never_mix` | I | Ingest with digest A, switch the lock to digest B for the same alias, ingest again. Search under B returns only B rows; the exact and semantic caches miss for B; `/v1/health` reports the A rows as stale. | A10, T10 |
| 6.4 | `tests/integration/test_vector_identity.py::test_rows_without_digest_are_stale` | I | A row written with the old provenance format counts as stale and is not returned by search. | A10 |
| 6.5 | `tests/unit/test_search_rerank_compat.py::test_deprecated_flag_is_ignored` | U | OpenAPI marks `rerank` deprecated. Requests with either value behave the same, and the flag is absent from exact and semantic cache keys. | A21 |

## WP7: Health, verifier, defaults, settings
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 7.1 | `tests/integration/test_health.py::test_health_makes_no_inference` | I | `GET /health` and `GET /v1/health` with `RecordingProvider`: zero requests; response keys unchanged from the 012 snapshot; `stale_vectors` present. | A10, A20 |
| 7.2 | `tests/unit/test_verifier_policy.py::test_verifier_uses_same_policy_checks` | U | Missing verifier refuses startup only when Agents is enabled. Local and hosted verifier attempts use admission, region and data-use checks; `verifier_must_be_local` denies a hosted verifier. | A12 |
| 7.3 | `tests/unit/test_settings.py::test_local_defaults` | U | `MODE=local`: chat `ollama/qwen3:4b-instruct-2507-q4_K_M`, fallbacks `["ollama/qwen3:1.7b"]`, embedding `ollama/nomic-embed-text`. | A14 |
| 7.4 | `tests/unit/test_docs_generated.py` (existing) | U | Passes with the new settings in `docs/configuration.md`. | A1 |

## WP8: Runtime, scripts and CI
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 8.1 | `tests/unit/test_compose.py::test_ollama_serves_read_only_store` | U | The `ollama` service mounts the model volume with `:ro`; `ollama-init` mounts it read-write and runs `check_lock.sh`; both images pinned by digest; runtime settings match the blueprint. | A4, A15 |
| 8.2 | `tests/unit/test_models_live.py::test_live_digest_check_is_conditional` | L | The live digest-binding test runs only when Ollama is available, invokes a locked model by `ollama/sha256:<digest>`, and fails if digest resolution fails. There is no nightly workflow. | A4 |
| 8.3 | live `scripts/verify/ollama.sh` | L | Architect-run: internal network, digest calls for chat, completion and embedding, mutation API refused, no egress. | A4, A15 |
| 8.4 | `tests/unit/test_models_live.py::test_hosted_smoke_skips_without_credentials` | U | `scripts/verify/hosted.sh` with no credential refs prints `SKIP`, exits 0 and never prints `PASS`. | A22 |
| 8.5 | captured `scripts/verify/hosted.sh` output | I | The Architect captures the command output for the missing-credential case. | A22 |

## WP9: UI
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 9.1 | `ui/src/features/decisions/decision-panel.test.tsx` › `shows model and stages for a model decision` | V | A decision with `extensions.model` and `extensions.stages` shows model identity and each stage in order with status and reason. | A13, A17 |
| 9.2 | `ui/src/features/decisions/decision-panel.test.tsx` › `old decisions show no model or stages` | V | `record_version: 1`, empty extensions: no Model block or stage list, no error. | A17 |
| 9.3 | `ui/src/features/trust/receipt-verifier.test.tsx` › `lists the signed model and stages fields` | V | A v2 receipt lists model and stage fields and verifies. A v1 receipt verifies as before. | A13, A17 |
| 9.4 | `ui/e2e/model-evidence.spec.ts` › `model decision to verified receipt` | P | Run a search, open its `model.invoke` decision in Evidence > Decisions, see the Model block and stage list, open the receipt in Trust > Verify, and it verifies. | A13, A17 |

## WP10: Benchmark and docs
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 10.1 | `tests/unit/test_decision_path_bench.py::test_benchmark_runs_at_tiny_size` | U | The script runs with a tiny iteration count and reports serial, 8-way and 32-way decisions per second plus p50/p95 added latency. | A18 |
| 10.2 | captured `scripts/bench/decision_path.py` output | I | The Architect runs the benchmark with a fake model and captures its full output. | A18 |
| 10.3 | captured CPU model profile command output | L | The Architect captures the real CPU profile run with latency p50/p95 and peak memory in `evidence/cpu-profile.txt`. | A14 |
| 10.4 | captured reranker-removal source and OpenAPI checks | U | The Architect captures the targeted source search and generated OpenAPI check in `evidence/reranker-removal.txt`. | A21 |
| 10.5 | captured deployment profile documentation check | U | The Architect captures the deployment document check showing CPU profile only and measured latency and memory. | A14 |

Docs checked by review and the existing doc tests: revised ADR-0014, CPU-only `docs/deployment.md`, `docs/configuration.md`, `docs/contracts/ports.md` (`ModelCatalog`), and `planning/program/conventions.md`.

## WP11: Evidence
Journey step: "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."
One captured command output per acceptance item. The Architect runs admissions, zero-inference, digest binding, CPU profile, Ollama isolation and benchmark checks against the real local stack where specified.
