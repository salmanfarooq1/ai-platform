# Sprint 026: Documents, retrieval and grounding. Requirements

Data pillar (M4, with the knowledge base in the Kernel). Better structure gives better retrieval, and answers come only from what the caller may see, with citations, or the system abstains. Documents are parsed offline into structured chunks and contract-shaped tables. This is a two-part sprint: part a covers items 1–4, part b covers items 5–8.

Source: old 030, plus new scope (data-pillar-retrieval-memory research note).

## Scope
1. **Docling `2.130.0`, offline.**
   - Layout and OCR weights are pre-fetched into a volume, and nothing is downloaded at runtime.
   - Only Apache-2.0 weights are used (decided 2026-10-11). TableFormer is taken under Apache-2.0, and if that does not hold, table structure is off.
   - Parsing runs in a worker with size and page limits.
2. **Structure-aware chunks.**
   - Chunks follow Docling's hierarchy (section, table, list) and carry heading path, page and box metadata.
   - Contextual retrieval (a short generated context prefix per chunk) is an ingest option, off by default, with its cost recorded.
   - New ports: `Parser` and `Chunker`. Re-ingesting existing documents is a job.
3. **True BM25 beside pgvector.**
   - `pg_textsearch` (PostgreSQL licence) replaces the `ts_rank` leg if it builds for our Postgres version. If it does not, `ts_rank` stays and is named as such (011).
   - Fusion is tuned on the labelled set and compared with RRF. The winner is a setting, and the result goes in evidence.
4. **Per-chunk ACLs.**
   - Each chunk stores the principal and group ids allowed to read it, set at ingest from the source (or from the knowledge base default).
   - An `AclFilter` in the `Retriever` resolves the caller's groups at query time (020 groups) and filters inside the index.
   - Stale or missing ACL data fails closed. The receipt records the ACL filter id.
5. **Grounding gate** (`Grounding` port).
   - A sufficiency check before answering: empty or weak retrieval means the system abstains with a clear message.
   - Span citations: each claim points to a chunk, page and box.
   - An NLI entailment check after generation. Unsupported claims are dropped or flagged.
   - The latency of the NLI check on a local model is measured. Its threshold is a placeholder.
6. **Evals.**
   - A labelled retrieval and grounding set on the reference company documents (dataset hash recorded).
   - RAGAS and TruLens run in CI tiers, with recall@k, citation precision and recall, abstention rate and faithfulness.
   - The 008 eval gate gains these metrics.
7. **Extraction to tables and review.**
   - Reference invoices and contracts are extracted into tables shaped by an ODCS contract (023).
   - A human approves, edits or rejects each extraction. Each field has a page and box citation drawn on the page image.
   - Approved rows publish through `DataAccess.submit_write` (the 022 write path).
8. **`ExternalIndex` adapter** for a client's existing vector store. The first adapter is a client pgvector, read-only, with the same `AclFilter` contract. OpenSearch, Elasticsearch and Azure AI Search are named as later adapters; Azure's document ACLs are still preview.
9. **Containment.** A malicious-PDF test shows extraction has no tool access and its output reaches only the review queue. Agent taint from document text starts in 027. ADR-0033.

## Out of scope
- GraphRAG and knowledge graphs (owner question Q-11; not planned).
- Formats other than PDF. User-defined extraction contracts beyond the two reference ones.
- Agent memory (028). Guard models on document text are in place from 019.
- Changed from old 030: document parsing now also feeds retrieval, and the taint test moves to 027 with the data agents.

## Nav placement
- Data > Documents: the review queue.
- Workspace > Library: chunk structure and ACLs per document.
- Governance > Evals: retrieval and grounding scores.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Placeholder thresholds (sufficiency, NLI, fusion weights) get questions.
