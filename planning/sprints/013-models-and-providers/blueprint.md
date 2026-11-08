# Sprint 013: Models and providers. Blueprint

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Based on the Sprint 012 worktree and the Ollama digest spike in `evidence/ollama-digest-spike.txt`.

## 1. The core rule: govern every physical attempt
Each physical model request has its own recorded allow. Request admission checks every alias the request may need before any inference. Admission allows do not grant runtime authority.

- An **attempt** is one request to one model at one endpoint: one completion, one chat turn or one embedding batch.
- An **admission** is an ordinary `enforce(MODEL_INVOKE, alias)` call with `extensions.model.phase = "admission"`. Search admits chat and embedding aliases. Agents admit reasoning and verifier aliases. MCP retrieval admits the aliases it uses. A denied admission stops the request before any model I/O.
- Before each attempt the caller resolves the model through the catalog, then calls `gateway.enforce()` with `Action(MODEL_INVOKE, resource=<alias>)` and the resolved identity as the record's `extensions.model`. Only on allow does it send the request, with exactly the resolved route.
- Retries and fallbacks live in `api/services/model_calls.py` (`ModelCaller`). Adapters make exactly one attempt and never retry. SDK retries are off: pass `num_retries=0` to LiteLLM, `max_retries=0` to OpenAI and Azure clients, and configure Bedrock for one attempt.
- A fallback is a separate attempt with its own resolution and its own allow. An allow for the primary never covers a fallback.
- If the decision cannot be written, the attempt is not sent (existing fail-closed rule, now per attempt).
- Workers authorize at execution time, per batch. The submit-time preflight in `POST /v1/ingest` stays as an early check but grants nothing at run time.

## 2. Typed seams (`ports/models.py`, new, strict mypy, no SDK imports)
```python
class ModelUse(str, Enum): COMPLETION = "completion"; CHAT = "chat"; EMBEDDING = "embedding"

@dataclass(frozen=True)
class ModelIdentity:
    alias: str                # the human name used in policy, pricing and display, e.g. "ollama/qwen3:4b-instruct-2507-q4_K_M"
    provider: str             # register key: "ollama", "azure-openai", "bedrock", "anthropic", "openai-compatible", "gemini", "groq"
    source: Literal["local", "hosted"]
    digest: str | None        # local only: "sha256:<64 hex>"
    provider_model_id: str | None  # hosted only: the reviewed model/version id
    processing_scope: str     # a register scope id; local models use DEPLOY_REGION
    storage_geography: str | None

@dataclass(frozen=True)
class ModelRoute:
    endpoint: str             # fixed base URL from settings or the lock; never from a request
    credential: SecretRef | None
    params: Mapping[str, JsonValue]   # frozen; e.g. {"num_ctx": 8192}
    fingerprint: str          # sha256 of canonical JSON of (identity, endpoint, credential reference name, params)

@dataclass(frozen=True)
class ResolvedModel:
    identity: ModelIdentity
    route: ModelRoute
    use: ModelUse
    price_ref: str | None     # key into MODEL_PRICING; None only for local (price 0)

class ModelCatalog(Protocol):
    async def resolve(self, alias: str, *, use: ModelUse) -> ResolvedModel: ...
    async def probe(self) -> CatalogHealth: ...   # metadata only, never inference
```
Typed failures in `ports/errors.py`: `UnknownModel`, `ModelDigestMismatch`, `UnpricedModel`, `ResidencyUnknown`. Each maps to a recorded deny before any provider I/O (reasons in section 6).

`ModelIdentity.as_extension(phase)` returns `{"name", "provider", "source", "digest" | "provider_model_id", "processing_scope", "route": <fingerprint>, "phase": "admission" | "attempt"}`. Every physical attempt and admission record includes this extension.

## 3. Secrets (`core/secrets.py`, new)
- `SecretRef` is `env:NAME` or `file:/abs/path`. Nothing else parses. No remote store.
- `resolve_secret(ref) -> Secret`. `Secret` has `reveal() -> str` and a `__repr__`/`__str__` of `Secret(<ref name>)`. Only adapters call `reveal()`.
- A `file:` ref must be a regular file, owned by the current user, not group- or world-readable, and not a symlink.
- Request bodies never carry credentials. Logs, records, errors and repr never contain a secret value (sentinel tests).

## 4. Catalog adapters
- `adapters/model_catalog.py`: `LockCatalog` (local models from `models.lock`), `RegisterCatalog` (hosted models from settings plus `providers.register.toml`), and `CompositeCatalog` that routes by alias prefix. A fake lives in `tests/fakes.py`. One contract suite runs on all three.
- **Local digest binding.** Ollama 0.40.7 resolves a local digest reference. The Architect's spike (`evidence/ollama-digest-spike.txt`) proved `sha256:<hex>` works for completion, chat, embeddings and the OpenAI-compatible API, through the locked LiteLLM as `ollama/sha256:<hex>` and `ollama_chat/sha256:<hex>`, and that an unknown digest fails with "not found". The `LockCatalog` sets the route model to `ollama/sha256:<digest>` (or `ollama_chat/...` for chat), so a re-tag of the alias cannot change what runs. As a second layer, the serving container mounts the model store read-only (section 8); the spike proved pull, copy and delete then fail.
- **Mismatch.** If the pulled digest differs from `models.lock`, `resolve` raises `ModelDigestMismatch` and the attempt is denied `model_digest_mismatch`.
- **Hosted.** `RegisterCatalog.resolve` fails with `UnpricedModel` when the alias has no `MODEL_PRICING` entry (every MODE, including local) and `ResidencyUnknown` when the register has no processing scope for the configured deployment.

## 5. Files reviewed in the repo
- `models.lock` (TOML). One `[[model]]` per local model: `alias`, `runtime` (`ollama`), `digest`, `licence` (SPDX id), `source` (URL), `size_bytes` and `use` (list of `ModelUse`).
  - Ollama: `qwen3:4b-instruct-2507-q4_K_M` (chat, completion), `qwen3:1.7b` (completion fallback), `nomic-embed-text:v1.5` (embedding).
  - All licences must pass the OSI allowlist from 011 (`scripts/supply_chain/osi-licences`). Qwen3 and nomic-embed-text v1.5 are Apache-2.0. The builder verifies each from the source link, not from this list.
- `providers.register.toml`. One `[provider.<key>]` per provider: `name`, `trains_on_data` (`"no" | "yes" | "unknown"` per tier), `retention`, `processing_scopes` (list of ids with a description each), `storage_geography`, `sources` (URLs), `reviewed` (date). Covers `ollama`, `gemini`, `groq`, `azure-openai`, `bedrock`, `anthropic`, `openai-compatible`. Unknown facts are written as `"unknown"`, and an unknown scope can never satisfy a region pin.
- The file name is recorded in `planning/program/conventions.md`.

## 6. Gateway and policy
- Stages run in this order: `principal, module, boundary, model, policy, guardrails, rate, budget, cost`. The `model` stage is after `boundary` and before `policy`, so a missing scope is denied before residency is checked.
- Policy gains `allowed_regions: list[str] | "*"` and `allowed_data_use: list[str] | "*"`, both defaulting to `"*"`. Register scopes map to region labels (`eu`, `us`, `global`, ...). A hosted scope of `unknown` is denied `residency_unknown` at stage `model`. Local models run in `DEPLOY_REGION`; startup refuses an unset region when a policy pin lists regions. A local attempt passes when its deployment region is in the pin or the pin is `"*"`.
- A provider marked as training on data or `unknown` is denied `data_use_not_allowed` at stage `policy` when `allowed_data_use` is a list.
- Bedrock validation derives its minimum processing scope from the model id prefix (`us.`, `eu.`, `apac.`, `global.`). Startup refuses a narrower configured scope.
- New reasons in `gateway/reasons.py`: `region_not_allowed` (stage `policy`, field `allowed_regions`), `model_digest_mismatch`, `model_unknown`, `model_unpriced`, `residency_unknown` (stage `model`), `model_breaker_open` (stage `model`), `model_concurrency_limit` (stage `rate`), `data_use_not_allowed` (stage `policy`) and `verifier_must_be_local` (stage `policy`).
- `evidence/extensions.py` registers closed schemas for `model` and `stages`. Model fields are `name`, `provider`, `source`, exactly one of `digest` or `provider_model_id`, `processing_scope`, `route` and `phase`. The stages value is an ordered list of `{stage, status, reason, duration_us}` objects. Status is `passed`, `denied`, `skipped` or `not_reached`; `reason` is a string or null. Both extensions are part of each signed v2 record, for every action and allow or deny.
- `enforce()` collects one stage entry in order. After a deny, later stages are `not_reached`. A stage that does not apply is `skipped`. Evidence > Decisions and the offline verifier show the stage list.
- The existing input guardrail also runs on `model.invoke`. It scans only caller-supplied input: the user's question or chat messages, including query text sent for embedding. Platform-built parts (system prompt, retrieved context) and ingest embedding batches are not scanned; the stage shows `skipped` for them. The tenant `max_query_length` cap is not applied to whole model prompts, because a synthesis prompt carries retrieved context; the context window bounds prompt size. It fails closed. Store only input hashes and matched rule ids. Reason: scanning platform-built text would deny normal synthesis and block legitimate documents; documents are governed at ingestion.
- Existing `allowed_models` policy keeps matching the alias.

## 7. Callers that change
| Path | Today | After |
|---|---|---|
| `api/services/llm.py` synthesis | 1 allow, up to 3 attempts | `ModelCaller.complete`: 1 allow per attempt, retries only on rate-limit errors, max 3 |
| `api/agent/graph.py` reasoning and verifier | 1 `_model_allowed` check | Admission for reasoning and verifier aliases; each physical call has its own allow. `VERIFIER_MODEL` may be local or hosted under the same policy checks. |
| `adapters/litellm_embeddings.py` fallbacks | loop inside the adapter | the loop moves to `ModelCaller.embed`; each target is its own attempt and allow; the result keeps the actual model and dimension |
| `core/pipeline/db_ingest.py` batches | no run-time allow | 1 allow per batch, under the job's enforcement context |
| `api/services/retriever.py` cross-encoder | unrecorded `predict` | Removed. The request field remains deprecated for one release and is ignored. |
| `api/routers/health.py` | embeds "health check" | `catalog.probe()` only; zero inference; same response schema |

Search, agent and MCP retrieval all go through `ModelCaller`, so they gain the same per-attempt records.

## 8. Local runtime
- `docker-compose.yml`, profile `models`: `ollama` keeps the pinned 0.40.7 image. Settings: `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=10m`, `OLLAMA_CONTEXT_LENGTH=8192`.
- `ollama-pull` becomes `ollama-init`: it pulls every model lock entry, then runs `scripts/models/check_lock.sh`, which compares the digests from `/api/tags` with the lock and exits non-zero on any difference.
- The serving container mounts the model volume read-only after init. Ollama's mutation API (pull, push, create, copy, delete) then fails at the filesystem.
- Ollama is reached only from the compose network and `127.0.0.1`. `scripts/verify/ollama.sh` proves it runs on an `internal: true` network with no egress.

## 9. Defaults and settings
- `_LLM_MODEL_DEFAULTS["local"] = "ollama/qwen3:4b-instruct-2507-q4_K_M"`. `public-preview` and `prod` are unchanged (out of scope).
- `VERIFIER_MODEL` defaults to the local chat model. It may be configured as hosted unless policy sets `verifier_must_be_local`.
- `config.py` `LLM_CONFIG["fallbacks"]`: `["ollama/qwen3:1.7b"]` for every mode. It is now read by `ModelCaller` (today it has no production reader).
- Embeddings stay `ollama/nomic-embed-text` v1.5, 768 dimensions.
- `MODEL_PRICING`: local models at 0. Hosted embedding prices stay an owner input (Q32 stays open for those).
- New settings: `VERIFIER_MODEL`, `DEPLOY_REGION`, `MODEL_ALLOWED_HOSTS` (application-level allowlist for hosted endpoints), `MODEL_MAX_CONCURRENT_PER_TENANT` (default 8), breaker thresholds, and `<PROVIDER>_CREDENTIAL_REF` per hosted provider. All validated in `core/settings.py` and listed in `docs/configuration.md`. `MODEL_ALLOWED_HOSTS` is not network egress control; that is Sprint 016.

## 10. Vector and cache identity
- The existing chunk provenance field stores `<alias>@<digest>` for local and `<alias>@<provider_model_id>` for hosted.
- Search filters, exact cache and semantic cache keys use that full identity. Two digests under one alias never share vectors or cached answers. Old rows with no digest count as stale until re-ingested; `/health` keeps reporting the stale count.

## 11. UI
- Evidence > Decisions: the decision panel shows a "Model" block and ordered stage list when extensions are present, and nothing for older rows.
- Trust > Verify a receipt: the signed fields list shows `extensions.model` and `extensions.stages`. The offline verifier prints stages. v1 receipts verify unchanged.
- No new page. Visible text follows `docs/design/` and the governed-design skill.

## 12. CI and profiles
- CI keeps the fake LLM. A live test runs only when Ollama is available, calls a locked model by `ollama/sha256:<digest>`, and fails if Ollama stops resolving digest references.
- A hosted smoke (`scripts/verify/hosted.sh`) runs only when a provider credential reference resolves; without one it prints SKIP and never PASS.
- `docs/deployment.md` documents the CPU profile with measured latency and memory from a real run.
- ADR-0014 (revised): local or hosted, the provider register, the model lock and the licence gate.

## 13. Out of scope
Unchanged from `requirements.md`.

## 14. Breaker, concurrency and benchmark
- One circuit breaker per route fingerprint, stored in Valkey. Open after 5 consecutive provider failures; half-open after 30 seconds with one trial. An open breaker denies `model_breaker_open` before I/O and allows fallback selection to continue.
- A Valkey lease caps attempts per tenant at `MODEL_MAX_CONCURRENT_PER_TENANT` (default 8). Over-limit attempts deny `model_concurrency_limit` at stage `rate`, before I/O. A lease expires if its process dies.
- `scripts/bench/decision_path.py` measures decisions per second (serial, 8 and 32 concurrent fake callers) and p50/p95 latency added by enforcement and record writes. A tiny test runs the script. Capture the real run in `evidence/decision-path-bench.txt`; no Sprint 013 target is set.
