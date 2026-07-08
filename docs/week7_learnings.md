# Week 7 Learnings: Hybrid RAG & Evaluation

## Lab 7.1: Vector Search Failure Cases

**Goal:** Understand why pure semantic search fails on specific query patterns, proving the need for a hybrid BM25 layer.

### Failure 1: Keyword specificity loss
- **Query:** `GDPR Article 5 data minimization principle`
- **What returned (snippet):** `[1] (Score: 0.69) ### Lawful Basis for Processing Under GDPR Article 6...`
- **Why vector search failed:** The embedding model compressed specific numbers/keywords ("Article 5", "minimization") into a generic "GDPR Data Rules" topic. It returned "Article 6" because it lives in the exact same semantic neighborhood.
- **What BM25 would do differently:** BM25 would search for the exact tokens `Article` + `5` + `minimization`. It would penalize chunks that don't contain these exact terms, preventing "Article 6" from matching. 

### Failure 2: Exact term retrieval
- **Query:** `what is the maximum fine under CCPA section 1798.155`
- **What returned (snippet):** *Nothing (empty results).*
- **Why vector search failed:** The vector search actually returned 5 garbage chunks, but our `SearchResponse` only populates `results` from the LLM's `citations`. Because the LLM cited nothing, our API swallowed the retrieved chunks, hiding the retrieval failure from the client. This is an architectural flaw: the API should return what retrieval found regardless of LLM generation.
- **What BM25 would do differently:** BM25 treats `1798.155` as a highly unique, rare token (high IDF). If it exists in the DB, it would instantly rank #1. If it doesn't, it safely returns 0 results at the database level, preventing semantic drift.

### Failure 3: Negation blindness
- **Query:** `HIPAA does NOT apply to which entities`
- **What returned (snippet):** *Nothing (empty results).*
- **Why vector search failed:** Embeddings are notoriously bad at negation. "Does NOT apply" and "Does apply" have >0.90 cosine similarity. Again, the DB returned 5 wrong chunks, but our API swallowed them because the LLM rejected them. 
- **What BM25 would do differently:** BM25 handles strict keyword presence/absence better, but negation is tricky for both. A cross-encoder (which we build in Lab 7.4) is required to truly understand negation syntax.

### Failure 4: Rare terminology
- **Query:** `legitimate interest assessment under GDPR recital 47`
- **What returned (snippet):** `[1] (Score: 0.67) # GDPR Compliance Policy` and `[2] Article 6...`
- **Why vector search failed:** "Recital 47" is a highly specific, rare term. Vector search diluted this into a generic "GDPR" query, returning broad policy headers rather than the specific recital text.
- **What BM25 would do differently:** "recital" and "47" are rare tokens. In TF-IDF/BM25 scoring, rare tokens carry massive weight. Any document containing them would blast to the top of the ranking. 

### Failure 5: Long-tail specificity
- **Query:** `data breach notification within 72 hours regulatory requirement`
- **What returned (snippet):** `[1] (Score: 0.87) ### Regulatory Notification Under GDPR Article 33...`
- **Why vector search succeeded (The argument FOR Hybrid):** Vector search crushed this! Score 0.87. Vector search effortlessly maps the concept of "72 hours" even if the text says "seventy-two hours", which would completely break a strict BM25 keyword search.
- **Why we need Hybrid:** This proves that replacing Vector with BM25 is not the answer. BM25 wins on exact matches (Failure 2), Vector wins on conceptual paraphrase (Failure 5). Hybrid gives us both.

## Lab 7.3: The Strict-AND vs Relaxed-OR Tradeoff in BM25

**Decision 10: Dynamic Query Operator Selection (Thresholding)**

In Postgres, `plainto_tsquery` separates all tokens with an `&` (AND). If a chunk is missing even a single word from the query, it is rejected entirely. 
- **The Problem:** This behavior causes BM25 to return 0 results for long, natural language queries (e.g. 6+ words), because the probability of all words appearing in a single chunk is extremely low.
- **The Tradeoff:** We could cast the query to text and blindly replace all `&` with `|` (OR) operators. This fixes recall for long queries, but completely sacrifices BM25's greatest strength: exact multi-term precision for short keyword queries (like "GDPR Article 5"). If we blindly used OR, "GDPR Article 5" would match any chunk that just mentions "GDPR", diluting the results.
- **The Solution:** We implemented a `BM25_OR_THRESHOLD = 5`. For queries under 5 words (keyword lookups), we use the strict `AND` operator to preserve extreme precision. For natural language queries with 5 or more words, we dynamically fall back to the `OR` operator to ensure high recall without returning empty sets.
