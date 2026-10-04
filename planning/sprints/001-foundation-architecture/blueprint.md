# Sprint 001: Blueprint

## Files to read
- `core/database/schema.sql`, `config.py`, `api/main.py`
- `api/middleware/rate_limit.py`, `api/agent/graph.py`, `api/routers/ingest.py`
- `core/ingestion/lifecycle.py`, `api/services/llm.py`, `core/clients/embeddings.py`

## Files (drafts already written by the Architect)
- `docs/architecture/FOUNDATION.md`
- `docs/adr/README.md`, `docs/adr/TEMPLATE.md`
- `docs/adr/0001`–`0005`
- `planning/ROADMAP.md`

## Steps
1. Check every file path and claim in `FOUNDATION.md` §1 against the code. Fix any that are wrong.
2. Check that every strict rule (§3) has at least one row in the check table (§4), with a sprint number.
3. Check that each ADR has a Status, Context, Decision, Consequences and at least one alternative.
4. Check that the sprint numbers in `ROADMAP.md`, `FOUNDATION.md` §4 and §5 agree.
5. Check that there are no dates or durations, and no brand or "demo" wording.

## Data model / API changes
None.

## Test plan
These are docs checks only: path existence, consistency greps (see `acceptance.md`).

## Walking-skeleton notes
This sprint defines the skeletons. Nothing is deferred inside it.
