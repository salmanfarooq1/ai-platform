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
**Decision:** Added a vector index in Redis (HNSW) so that before doing a full DB + LLM round trip, we check if any previously cached query is semantically close enough (cosine > 0.95) to serve the same answer. Hit rate went from 41% to 74% on the same query set.
**Trade-off:** You need to embed the query before checking the cache, which costs ~10ms. But you were going to embed it for vector search anyway, so you compute it once and use it for both. The 0.95 threshold took some tuning — at 0.85 precision visibly dropped (wrong answers served), at 0.99 it collapses back to string matching. 0.95 was the empirical sweet spot.

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

## Known Open Gaps (Deferred by Design)

- **Citation content validation:** Code checks that chunk_index exists, not that the cited chunk truly supports the answer. Resolved in Week 7 via RAGAS faithfulness scoring.
- **Budget hard stop:** Monthly LLM spend is tracked in logs but not enforced with a hard cap. Redis counter approach planned for Week 9.
- **Semantic cache quality monitoring:** No automated check that 0.95 threshold isn't serving wrong answers. Manual log review interim. Automated spot-checking deferred to Week 8.
- **Full CDC cache invalidation:** Cache invalidation on document update deferred to Week 10. TTL=3600s mitigates for low-change-frequency documents.

