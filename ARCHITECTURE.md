# Architecture Decisions

## Decision 1: run_in_executor for CPU-bound work (Week 4)
**Context:** Fast API is single-threaded, running CPU bound tasks directly would block the event loop.
**Decision:** `run_in_executor()` runs CPU-bound tasks in a saperate process, event loop stays free.
**Trade-off:** cost, pickle and unpickle overhead, only tasks taking more than ~10ms are worth it. 

## Decision 2: Domain-Specific Chunking Strategy (Week 4)
**Context:** Single chunking strategy is inefficient for all document types. An OpenAPI spec needs different chunking than a regular pdf document. 
**Decision:** `CHUNKER_REGISTRY` dispatches by file extension. 
- .txt/.md: `recursive`/`header-aware split`.
- .json : `chunk_openapi_spec` (one operation per chunk)
**Trade-off:** Document type has to be detected at ingestion time, a mislabled file with wrong extension would fall back to default chunker.

## Decision 3: LiteLLM over Langchain/custom LLM router (Week 5)
**Context:** Each LLM provider has it's own auth, response format etc. yet LLM calls must be standardized. The goal is replace code changes with config changes. 
**Decision:** LiteLLM, provides `acompletion()` function, standard way to call any LLM. Any future model change would require a simple config change.
**Trade-off:** LiteLLM is still a dependency that might break, mitigated by pinning the version.
 - Why not Langchain: Langchain is an orchestration layer.LiteLLM is just a model access layer. Langchain has its provider routing coupled with own objects such as `BaseMessage`, `Runnables`, which add abstraction and complexity, while limiting our flexibility.   

## Decision 4: Structured Outputs over regex parsing (Week 5)
**Context:** LLM outputs need to be parsed, but they are prone to hallucinations and inconsistent formatting. Regex is brittle in these scenerios.
**Decision:** Structured outputs by using `GeneratedAnswer = response_format()`. LLM output is constrained at decoding level and validated by Pydantic.
**Trade-off:** Not every llm supports structured outputs, the fallback is Json mode with validation. There is still a risk of well-structured hallucination, it may provide a fabricated chunk_id.

## Decision 5: Inline citations, RAGAS vs user trust (Week 5)
**Context:** RAGAS already measures faithfulness, yet it is developer-facing. We need a user-facing trust system, most of regulated industries need this for audit trails and compliance.
**Decision:** Inline citations, this provides answers traced back to actual sources through chunk_id. 
**Trade-off:** Citations add 20% more tokens, including chunk_ids and instructions. Another option is post-hoc citation matching with embedding similarity, this saves tokens but adds extra layer with moving parts, adding a dependency on similarity search. Inline citations also are prone to hallucination, LLM can provide a chunk_id that does not actually back up the source, and RAGAS cannot verify this because it looks in different direction.

## Decision 6: Semantic cache over exact-match cache (Week 6)
**Context:** After wiring up basic Redis caching, the hit rate was around 40%. The reason: queries like "what is AI?" and "explain artificial intelligence" are treated as completely different keys. They miss the cache every time even though they'd get identical answers.
**Decision:** Added a vector index in Redis (HNSW) so that before doing a full DB + LLM round trip, we check if any previously cached query is semantically close enough (cosine similarity > 0.65) to serve the same answer. Hit rate went from 41% to 74% on the same query set.
**Trade-off:** You need to embed the query before checking the cache, which costs ~10ms. But you were going to embed it for vector search anyway, so you compute it once and use it for both. The 0.65 threshold took tuning — at 0.55 precision dropped (wrong answers served), at 0.95 it collapsed back to near-exact string matching with <5% improvement over exact cache. 0.65 was the empirical sweet spot measured in Lab 6.2.

## Decision 7: Heuristic model routing by query complexity (Week 6)
**Context:** Running every query through the most expensive model is wasteful. A question like "what is the return policy?" and "compare GDPR and CCPA fine structures across jurisdictions" are not the same problem. They shouldn't cost the same.
**Decision:** A simple word count + keyword heuristic classifies queries as simple or complex before the LLM call. Simple queries go to the cheaper/local model. Complex ones go to the configured production model.
**Trade-off:** The heuristic is obviously imperfect — a short question can be conceptually hard, a long one can be trivial. The risk is misclassification giving a poor answer on a simple-looking but complex question. Acceptable for now because the quality gap between models is smaller than it looks for this corpus. Something like a small classifier or LLM-based routing would be the real fix, deferred.

## Decision 8: TTL-based cache invalidation over full CDC (Week 6)
**Context:** Once an answer is cached, what happens when the source document changes? A user could get a cached response about a compliance policy that was updated last week and we'd never know.
**Decision:** Cache TTL is set to 3600 seconds (1 hour). Documents in this system change quarterly at most, so 1 hour staleness is an acceptable window. When a document is replaced, the document_id changes, which means old chunks are deleted and the new ones will naturally miss cache and repopulate it.
**Trade-off:** This is not full CDC. Proper invalidation would tag every cache entry with its source document_id and delete on document update. That's architecturally correct but complex to implement. TTL is the interim mitigation — it's simple, proven, and fine for low-change-frequency documents. Full invalidation is planned for Week 10 when the document lifecycle module is built.

## Decision 9: Hybrid RRF over pure vector or pure BM25 (Week 7)
**Context:** After running Lab 7.1, I documented 5 concrete failure modes of pure vector search on the legal corpus. Article numbers like "Article 5" drift to "Article 6" because they sit in the same semantic neighborhood. Section identifiers like "1798.155" return garbage because embeddings compress rare tokens into generic topics. Negation ("does NOT apply") is essentially invisible to cosine similarity.
**Decision:** Hybrid RRF (Reciprocal Rank Fusion with k=60) merges vector results and BM25 results by rank position, not by score. Neither retriever dominates — a document scoring well in either list gets a lift. This fixes the failure modes above without throwing away semantic search's strength on paraphrase queries.
**Trade-off:** RRF doesn't use the raw scores from either retriever — it only uses rank position. So a BM25 result with score 0.9 and one with score 0.4 look identical to RRF as long as they're at the same rank. This is intentional (it prevents one retriever's score scale from overwhelming the other) but it means you lose score magnitude information. k=60 was benchmarked against k=20 and k=100 — it's the literature default and gave the best empirical precision on this corpus.

## Decision 10: Dynamic AND/OR operator in BM25 based on query length (Week 7)
**Context:** PostgreSQL's `plainto_tsquery` connects all tokens with AND by default. For short keyword queries like "GDPR Article 5", this is exactly what you want — strict intersection, maximum precision. But for a 7-word natural language question, the probability of all tokens appearing in a single chunk drops close to zero. BM25 was returning empty results on every conversational query.
**Decision:** `BM25_OR_THRESHOLD = 5`. Queries under 5 words use the strict AND operator — precision mode. Queries with 5+ words dynamically rewrite the tsquery from AND to OR — recall mode. This is a one-line change in SQL but it fundamentally changes the retriever's behavior based on query intent.
**Trade-off:** The threshold of 5 is a heuristic. A 4-word query could be conversational, a 6-word query could be a precise identifier lookup. The failure mode in either direction is manageable though — false ANDs produce empty results (obvious failure), false ORs produce extra candidates which the cross-encoder then re-ranks down. Reranking partially saves us from over-broad BM25.

## Decision 11: Cross-encoder reranking enabled in production, disabled in demo (Week 7)
**Context:** After hybrid RRF, answer relevancy was 0.7983 for the RRF-only mode. Adding the cross-encoder reranker jumped it to 0.9167 — a meaningful +0.12 improvement. The model is `cross-encoder/ms-marco-MiniLM-L-6-v2`, runs locally with no API cost. But it takes ~380ms for inference, which blocks the event loop if called directly inside an async handler.
**Decision:** Reranking runs via `run_cpu_bound()` — offloaded to a `ProcessPoolExecutor`. Lab 7.5 confirmed that in offloaded mode, the event loop heartbeat max gap is 11ms, well under the 20ms safe threshold. So `rerank=True` is the default in production. In the demo deployment (Fly.io, 256MB RAM), reranking is disabled — the model alone is ~200MB and would OOM the container. Demo mode uses RRF-only, which still significantly outperforms pure vector.
**Trade-off:** The cross-encoder scores are raw logits — unbounded, not in [0,1]. We deliberately don't expose `rerank_score` as the confidence value in the API response because showing an unbounded logit as a percentage would be misleading. Only `rrf_score` is surfaced as the relevance signal. Reranking changes ordering silently, which is correct behavior.

## Decision 12: Rate Limiting Middleware (Week 8)
**Context:** We needed a way to prevent API abuse and control costs per tenant namespace. Relying solely on the database or downstream LLM provider for rate limits exposes the app layer to unbounded resource consumption.
**Decision:** We implemented a LIFO `RateLimitMiddleware` using a fixed-window counter in Redis (`INCR` + `EXPIRE`). Limits are enforced at the outermost layer of the application per `namespace`.
**Trade-off:** Fixed-window limits are susceptible to burst traffic at the edge of the window. A sliding window would be more accurate but adds complexity and performance overhead. For our scale, fixed-window is a pragmatic choice.

## Decision 13: Document Lifecycle & Content Hashing (Week 8)
**Context:** Re-ingesting the same document repeatedly wastes vector storage and embedding tokens. We needed a mechanism to detect duplicate content and handle document replacement cleanly without leaving orphaned chunks.
**Decision:** We use SHA-256 content hashing to fingerprint documents upon ingestion. The hash and status are tracked in a `document_registry` table using a composite primary key `(document_id, namespace)`. When a document is updated, its prior chunks are explicitly deleted before re-embedding.
**Trade-off:** Computing SHA-256 requires reading the file payload, which adds slight latency to ingestion. However, it completely eliminates duplicate processing costs, which far outweigh the hashing overhead.

## Decision 14: Multi-stage Docker build (Week 9)
**Context:** The application has heavy dependencies (sentence-transformers, numpy, PyTorch). A naive Dockerfile produces a 2-3GB image. Cloud deployment platforms have limited disk space on free tiers, and image pull time directly impacts cold start latency.
**Decision:** Two-stage build. Builder stage installs Poetry and resolves all dependencies. Runtime stage copies only the virtualenv and application code. Result: ~600MB image (still large due to PyTorch, but 60% smaller than single-stage).
**Trade-off:** Multi-stage builds are more complex to debug (you cannot `docker exec` into the builder stage). If a dependency fails to build, you need to add a `RUN` step in the builder stage to diagnose it. Worth it for the image size reduction.

## Decision 15: Daily token budget via Redis INCRBY (Week 9)
**Context:** FinOps middleware tracks cost per request but does not enforce a cap. A runaway script or misconfigured agent can exhaust the Groq API quota before anyone notices.
**Decision:** A Redis counter keyed by `budget:{namespace}:{date}` tracks cumulative tokens per namespace per day. The middleware checks the counter before processing and rejects with 429 when the budget is exceeded. The key expires after 25 hours (self-cleaning, no cron).
**Trade-off:** The budget check adds one Redis GET to every /search request (~0.1ms). The counter is eventually consistent — two concurrent requests could both pass the check and both consume tokens, briefly exceeding the cap by up to one request's worth. Acceptable for a compliance platform with moderate query volume.

## Decision 16: LangGraph agent: reasoning/retrieval role, deterministic synthesis, optional verifier role (Week 10)
**Context:** Some compliance questions require multi-step reasoning. "Compare GDPR and CCPA breach notification timelines" needs two separate retrievals and a synthesis step, the single-shot `/search` pipeline cannot do this in one call. Confidently-wrong answers are also a specific risk for a compliance product.
**Decision:** A single LangGraph graph with two LLM-invoked tools (`retrieve_chunks`, parameterized by `mode` rather than split per strategy; `list_namespaces` for discovery), a deterministic synthesis node that always runs via the same `generate_with_routing()` `/search` uses, and an optional verifier node that checks the drafted answer against retrieved chunks before returning it. The verifier is a second LLM role, not a second framework or agent-team, toggleable per request (`enable_verifier`) and with a deployment-wide kill-switch (`FEATURES["verifier_enabled"]`). Exposed at `/agent/query`.
**Why one reasoning role, not several:** A namespace-per-agent or strategy-per-tool split would be additional LLM calls doing what one parameterized call already does, with no new capability. The verifier is different: checking an answer against its sources is a distinct skill from producing the answer.
**Trade-off:** Agent queries are 2-5x slower than direct `/search` even without verification; with verification enabled (default) and a retry triggered, that multiplies further. Acceptable for complex research questions; simple factual queries should still use `/search`, and verification can be turned off per request when latency matters more. All LLM calls in the graph flow into `request.state.usage` alongside synthesis cost, so FinOps sees a query's full cost.

## Known Open Gaps (Deferred by Design)

- **Real-time citation content validation:** The code validates that a `chunk_id` exists in the database, but does not run an LLM check on the live path to prove the chunk content strictly entails the sentence. Doing this synchronously would add 300ms+ latency and double LLM token cost per request. Offline DeepEval faithfulness scoring (Week 7) measures citation quality in batch. Live citation validation is deferred.
- **Monthly aggregate budget caps:** Daily LLM spend is tracked and capped in Redis (Week 9) to prevent catastrophic runaway costs. Monthly aggregation and billing tier logic require persistent DB rollups and accounting rules, which are deferred because daily caps mitigate 99% of financial risk.
- **Event-driven CDC cache invalidation:** Cache invalidation uses TTL=3600s. Real-time CDC (Change Data Capture) via Postgres triggers or Redis Pub/Sub would immediately invalidate cached queries when a document changes, but adds background worker complexity. Because compliance documents update quarterly at most, TTL expiry combined with SHA-256 document lifecycle management (Week 8) is an acceptable tradeoff. CDC invalidation is deferred.
- **`fetch_full_document` tool (Week 10):** For when a 500-character chunk is not enough surrounding context. Needs to be confirmed against the actual `documents` table schema before building to ensure reassembly by chunk order sorts on how `chunk_index` is actually stored (e.g. inside a metadata JSON column), not row insertion order. Deferred to future work.
- **FinOps persistent storage code (Week 10):** It is still unresolved whether usage is persisted per-request (allowing monthly cost rollups via a free date-range query) or only kept as a resetting counter (which would create a real, unrecoverable monthly gap). Deferred until this architecture detail is clarified.

