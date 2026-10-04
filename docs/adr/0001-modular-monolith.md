# ADR 0001: Modular monolith

**Status:** Accepted

## Context
- The platform needs gateway, knowledge, agent, workflow, data and trust capabilities.
- It runs on one free-tier instance (512MB RAM).
- Today it is a single FastAPI app (`api/main.py`) with no internal module boundaries enforced.

## Decision
- Build **one deployable app with strict internal modules**: `gateway`, `knowledge`, `agents`, `workflows`, `data`, `trust`.
- Modules call each other only through each module's public interface: typed functions and Pydantic models.
- A module never reads another module's tables.
- The gateway is the one module designed from the start to run as its own process later (ADR-0004).

## Consequences
- One deploy, one trace, and cheap hosting.
- Module boundaries must be enforced by an import-lint rule (Sprint 005), or they will erode.
- Splitting out a service later is a deployment change, not a rewrite.

## Alternatives considered
- **Microservices now:** more deploys, network hops and cost, with no scale need yet.
- **Unstructured monolith (status quo):** cheap now, but expensive to split later.
