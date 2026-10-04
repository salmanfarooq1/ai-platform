# ADR 0005: Ports and adapters for external providers

**Status:** Accepted

## Context
- Providers are chosen by LiteLLM model strings spread across `api/services/llm.py`, `core/clients/embeddings.py` and `api/agent/graph.py`.
- There is no embedding fallback.
- The vector column is fixed at `VECTOR(768)`, and nothing records which model produced each vector.

## Decision
- Define ports (Python `Protocol`s) for `LLM`, `Embedder`, `VectorStore`, `ObjectStore` and `JobQueue`. Each concrete provider is an adapter, selected by config.
- Only adapter modules may import provider SDKs, and an import-lint rule enforces this.
- Every stored vector records the embedding model and dimension that produced it.

## Consequences
- Swapping a provider is a config change, and tests use fake adapters.
- A re-embed can run alongside the old vectors, because vectors are versioned by model.
- Adds a thin layer of interfaces to maintain.

## Alternatives considered
- **LiteLLM strings everywhere (status quo):** they lock call sites to one library and make faking harder.
- **A heavy framework abstraction:** more surface than needed.
