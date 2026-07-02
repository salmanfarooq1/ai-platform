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

## Decision 6: Why semantic cache over string-only cache
**Context:** Exact-match cache misses on paraphrases
**Problem:** "What is AI?" and "Explain artificial intelligence" are the same intent
**Solution:** Redis vector index with cosine similarity threshold 0.95
**Trade-off:** Requires embedding computation before cache check (but you already need it for search)

## Decision 7: Why model routing by query complexity
**Context:** Not every query needs the most expensive model
**Problem:** GPT-4o costs 17x more per output token than Groq Llama 3.1 70B
**Solution:** Heuristic classifier routes simple queries to cheap models
**Trade-off:** Risk of quality degradation on misclassified queries
