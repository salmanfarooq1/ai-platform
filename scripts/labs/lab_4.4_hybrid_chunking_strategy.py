"""
hybrid_chunking_strategy.py
============================
Lab 4.4b — Production chunking strategies for the ai-platform ingestion pipeline.

Each strategy produces list[ChunkRecord] — a structure ready to insert into
the documents table (content TEXT, embedding VECTOR(768), metadata JSONB).
The embedding field is left as None here; embedders.py fills it downstream.

Strategies:
  - recursive_split()     .txt, prose, general docs       ← implemented
  - header_aware_split()  .md files                       ← implemented
  - chunk_openapi_spec()  .json OpenAPI specs             ← implemented
  - semantic_split()      long docs with topic shifts     ← STUB, needs embedder

NOTE on chunk_size units:
  Using characters, not tokens. Token counting requires a tokenizer (tiktoken
  or model-specific). At 4 chars ≈ 1 token for English prose, chunk_size=1200
  chars ≈ 300 tokens — a reasonable working size for most embedding models.
  TODO: replace with tiktoken when tokenizer is wired into the pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable as _Callable
import json as _json
import re
import time
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# ChunkRecord — maps directly to the documents table schema
# ---------------------------------------------------------------------------

@dataclass
class ChunkRecord:
    """
    One row ready for insertion into the documents table.

    Fields map to schema:
      content   → TEXT       the text that gets embedded
      embedding → VECTOR(768) None here; embedders.py fills this
      metadata  → JSONB      everything needed for citation + filtering

    Why a dataclass and not a dict:
      Autocomplete works. Typos in field names are caught at definition time,
      not silently at insert time. Adding a field here shows up everywhere.
    """
    content:   str
    metadata:  dict         = field(default_factory=dict)
    embedding: list[float] | None = field(default=None, repr=False)

    def __post_init__(self):
        self.content = self.content.strip()

    def __repr__(self) -> str:
        preview = self.content[:60].replace("\n", " ")
        return (
            f"ChunkRecord("
            f"chars={len(self.content)}, "
            f"index={self.metadata.get('chunk_index', '?')}/"
            f"{self.metadata.get('chunk_total', '?')}, "
            f"source='{self.metadata.get('source', 'unknown')}', "
            f"preview='{preview}...')"
        )


# ---------------------------------------------------------------------------
# Strategy 1: Recursive split
# For: .txt, prose, general documentation
# ---------------------------------------------------------------------------

def recursive_split(
    text:       str,
    source:     str | Path = "unknown",
    chunk_size: int = 1200,     # characters (~300 tokens for English prose)
    overlap:    int = 100,      # characters carried over to next chunk
) -> list[ChunkRecord]:
    """
    Split text by trying paragraph boundaries first, then sentences, then
    characters. Keeps the highest-level semantic boundary that fits within
    chunk_size.

    Args:
        text:       full document text
        source:     filename or path — stored in metadata for citation
        chunk_size: max characters per chunk (~300 tokens at 4 chars/token)
        overlap:    characters of context carried into the next chunk.
                    Prevents a sentence split from losing context at boundaries.

    Returns:
        list[ChunkRecord] with content + metadata, embedding=None

    Why this order (paragraph → sentence → character):
        Paragraphs are the strongest semantic unit in prose. If a paragraph
        fits, keep it whole. If not, fall back to sentence boundaries. Only
        split mid-sentence as a last resort for very long sentences.
    """

    def _split_recursive(text: str, separators: list[str]) -> list[str]:
        """
        Recursively split text using the first separator that produces
        chunks within chunk_size. Falls back to next separator if needed.
        """
        if not separators:
            # Base case: character split with overlap
            segments, start = [], 0
            while start < len(text):
                segments.append(text[start:start + chunk_size])
                start += chunk_size - overlap
            return segments

        sep = separators[0]
        parts = [p.strip() for p in text.split(sep) if p.strip()]
        segments, current = [], ""

        for part in parts:
            candidate = (current + sep + part).strip() if current else part

            if len(candidate) <= chunk_size:
                # Still fits — keep accumulating
                current = candidate
            else:
                if current:
                    segments.append(current)
                # This part alone is too big — recurse with next separator
                if len(part) > chunk_size:
                    segments.extend(_split_recursive(part, separators[1:]))
                    current = ""
                else:
                    current = part

        if current:
            segments.append(current)

        return segments

    raw_segments = _split_recursive(
        text,
        separators=["\n\n", ". ", "! ", "? ", " "]
    )

    # Filter empty — track precise char positions during iteration (not text.find
    # which breaks on repeated content)
    valid, char_positions = [], []
    cursor = 0
    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue
        # Advance cursor to where this segment actually starts in original text
        pos = text.find(seg, cursor)
        if pos == -1:
            pos = cursor   # fallback — shouldn't happen
        valid.append(seg)
        char_positions.append(pos)
        cursor = pos + len(seg)

    total = len(valid)

    return [
        ChunkRecord(
            content=segment,
            metadata={
                # Citation fields — shown to the user in retrieval results
                "source":        str(source),
                "filename":      Path(source).name if source != "unknown" else "unknown",
                # Position fields — reconstruct document order from DB
                "chunk_index":   i,
                "chunk_total":   total,
                "char_start":    char_positions[i],
                "char_end":      char_positions[i] + len(segment),
                # Chunker config — debug retrieval issues, reproduce chunking
                "strategy":      "recursive",
                "chunk_size":    chunk_size,
                "overlap":       overlap,
                "word_count":    len(segment.split()),
            }
        )
        for i, segment in enumerate(valid)
    ]


# ---------------------------------------------------------------------------
# Strategy 2: Header-aware split
# For: .md files — markdown documentation, READMEs, wikis
# ---------------------------------------------------------------------------

def header_aware_split(
    text:       str,
    source:     str | Path = "unknown",
    chunk_size: int = 1200,
    overlap:    int = 100,
) -> list[ChunkRecord]:
    """
    Split markdown using header boundaries (# ## ###) as the primary split point.
    Each header + its body content = one logical chunk.

    If a section's content exceeds chunk_size, falls back to recursive_split
    on that section's body — but keeps the full header hierarchy in metadata
    so every sub-chunk still knows "I came from ## Architecture > ### Database".

    Args:
        text:       full markdown document text
        source:     filename or path — stored in metadata for citation
        chunk_size: max characters per chunk before fallback split kicks in
        overlap:    passed to recursive_split when fallback is needed

    Metadata per chunk (strategy-specific fields):
        header          — the immediate header title above this chunk
        header_level    — 1/2/3 corresponding to #/##/###
        header_path     — full hierarchy e.g. "Overview > Architecture > Database"
                          critical for citation: tells user exactly where in the
                          doc this chunk came from
        section_index   — position of this section among all top-level sections
        is_subsection   — True if this chunk came from a sub-header split

    Why header_path matters:
        A chunk titled "Configuration" is ambiguous. "Setup > Installation >
        Configuration" is a precise citation. header_path gives you that.
    """

    # --- Parse markdown into sections ---
    # Each section is (level, title, body_text, char_start)
    header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    sections = []
    matches  = list(header_pattern.finditer(text))

    for idx, match in enumerate(matches):
        level = len(match.group(1))     # number of # chars
        title = match.group(2).strip()
        start = match.start()
        # Body runs from end of this header line to start of next header
        body_start = match.end()
        body_end   = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body       = text[body_start:body_end].strip()

        sections.append({
            "level":  level,
            "title":  title,
            "body":   body,
            "char_start": start,
        })

    # Handle documents with no headers — fall back to recursive
    if not sections:
        chunks = recursive_split(text, source=source, chunk_size=chunk_size, overlap=overlap)
        for c in chunks:
            c.metadata["strategy"]       = "header_aware_fallback"
            c.metadata["fallback_reason"] = "no headers found in document"
        return chunks

    # --- Build header hierarchy (header_path) ---
    # Track current heading at each level to construct full path
    # e.g. if we're in ### Database under ## Architecture under # Overview:
    # header_path = "Overview > Architecture > Database"
    current_headers: dict[int, str] = {}

    def build_header_path(level: int, title: str) -> str:
        current_headers[level] = title
        # Clear any deeper levels (we've moved to a new section at this level)
        for deeper in list(current_headers.keys()):
            if deeper > level:
                del current_headers[deeper]
        path_parts = [current_headers[l] for l in sorted(current_headers)]
        return " > ".join(path_parts)

    # --- Build chunks ---
    chunks: list[ChunkRecord] = []
    section_index = 0

    for sec in sections:
        header_path = build_header_path(sec["level"], sec["title"])
        full_content = f"{'#' * sec['level']} {sec['title']}\n\n{sec['body']}".strip()

        base_metadata = {
            # Citation fields
            "source":         str(source),
            "filename":       Path(source).name if source != "unknown" else "unknown",
            # Header hierarchy — the key metadata this strategy adds
            "header":         sec["title"],
            "header_level":   sec["level"],
            "header_path":    header_path,
            # Position
            "section_index":  section_index,
            "char_start":     sec["char_start"],
            # Chunker config
            "strategy":       "header_aware",
            "chunk_size":     chunk_size,
            "overlap":        overlap,
        }

        if len(full_content) <= chunk_size:
            # Section fits — one clean chunk
            chunks.append(ChunkRecord(
                content=full_content,
                metadata={
                    **base_metadata,
                    "chunk_index":    0,
                    "chunk_total":    1,
                    "char_end":       sec["char_start"] + len(full_content),
                    "word_count":     len(full_content.split()),
                    "is_subsection":  False,
                }
            ))
        else:
            # Section too large — recursive fallback on body only
            # Header line goes into every sub-chunk's metadata, not its content
            sub_chunks = recursive_split(
                sec["body"], source=source,
                chunk_size=chunk_size, overlap=overlap
            )
            for sub in sub_chunks:
                sub.metadata.update({
                    **base_metadata,
                    # Override position fields from recursive with section-level ones
                    "chunk_index":   sub.metadata["chunk_index"],
                    "chunk_total":   sub.metadata["chunk_total"],
                    "is_subsection": True,
                    "word_count":    len(sub.content.split()),
                })
            chunks.extend(sub_chunks)

        section_index += 1

    # Final pass — set chunk_total across the whole document
    total = len(chunks)
    for i, c in enumerate(chunks):
        c.metadata["doc_chunk_index"] = i
        c.metadata["doc_chunk_total"] = total

    return chunks


# ---------------------------------------------------------------------------
# Strategy 3: OpenAPI-aware split
# For: .json OpenAPI / Swagger specs
# ---------------------------------------------------------------------------

def chunk_openapi_spec(
    text:       str,
    source:     str | Path = "unknown",
    chunk_size: int = 1200,
) -> list[ChunkRecord]:
    """
    One ChunkRecord per API operation (path + HTTP method).

    Accepts raw JSON string — parses internally so callers never
    touch json.loads. One operation = one self-contained queryable unit.

    If the rendered chunk exceeds chunk_size, the chunk is kept whole
    (splitting an operation mid-schema breaks semantic completeness) but
    flagged with oversize=True in metadata so the retrieval layer can
    log, monitor, or truncate at query time.

    Metadata per chunk:
        method          str   "post", "get", "delete" …
        path            str   "/api/v1/documents"
        operation_id    str   "createDocument" — None if absent
        summary         str   human-readable one-liner — "" if absent
        tags            list  ["documents", "ingestion"] — filterable
        has_request_body bool  True if operation defines a requestBody
        response_codes  list  ["200", "404", "422"]
                              stored as JSONB array → queryable with
                              PostgreSQL ?| operator:
                                metadata->'response_codes' ?| array['404','500']
        oversize        bool  True when len(content) > chunk_size
                              chunk is NOT truncated — just flagged
    """
    # --- Parse ---
    try:
        spec = _json.loads(text)
    except _json.JSONDecodeError as exc:
        raise ValueError(
            f"chunk_openapi_spec: invalid JSON in '{source}' "
            f"— {exc.msg} at line {exc.lineno}, col {exc.colno}"
        ) from exc

    if not isinstance(spec, dict):
        raise ValueError(
            f"chunk_openapi_spec: expected JSON object, got {type(spec).__name__}"
        )

    paths = spec.get("paths", {})
    if not paths:
        # Valid spec but no endpoints — return empty, not an error
        return []

    # Path-level parameters inherited by all operations under that path
    # (OpenAPI 3.x allows parameters at the path object level)
    HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

    chunks: list[ChunkRecord] = []
    op_index = 0
    total_ops = sum(
        1
        for methods in paths.values()
        for method in methods
        if method.lower() in HTTP_METHODS
    )

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        # Path-level shared parameters (inherited by all operations here)
        path_params = path_item.get("parameters", [])

        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue  # skip 'summary', 'description', 'parameters' at path level
            if not isinstance(operation, dict):
                continue

            # --- Extract fields ---
            operation_id = operation.get("operationId")          # may be None
            summary      = operation.get("summary", "")
            description  = operation.get("description", "")
            tags         = operation.get("tags", [])

            # Merge path-level + operation-level parameters
            op_params   = operation.get("parameters", [])
            all_params  = path_params + op_params

            request_body     = operation.get("requestBody", {})
            has_request_body = bool(request_body)

            responses     = operation.get("responses", {})
            response_codes = [str(code) for code in responses.keys()]

            # --- Build human-readable chunk text ---
            # Readable format produces better embeddings than raw JSON.
            lines = [
                f"Endpoint: {method.upper()} {path}",
            ]
            if operation_id:
                lines.append(f"Operation ID: {operation_id}")
            if summary:
                lines.append(f"Summary: {summary}")
            if description and description != summary:
                lines.append(f"Description: {description}")
            if tags:
                lines.append(f"Tags: {', '.join(tags)}")

            if all_params:
                lines.append("\nParameters:")
                for p in all_params:
                    if not isinstance(p, dict):
                        continue
                    name     = p.get("name", "?")
                    location = p.get("in", "?")       # query/path/header/cookie
                    required = p.get("required", False)
                    p_desc   = p.get("description", "")
                    req_str  = "required" if required else "optional"
                    line     = f"  - {name} ({location}, {req_str})"
                    if p_desc:
                        line += f": {p_desc}"
                    lines.append(line)

            if has_request_body:
                content_types = list(request_body.get("content", {}).keys())
                rb_required   = request_body.get("required", False)
                lines.append(
                    f"\nRequest Body: {', '.join(content_types) or 'unspecified'}"
                    f"{' (required)' if rb_required else ''}"
                )
                # Include schema summary if present — valuable for retrieval
                for ct, ct_obj in request_body.get("content", {}).items():
                    schema = ct_obj.get("schema", {})
                    if schema:
                        lines.append(
                            f"  Schema: {_json.dumps(schema, separators=(',', ':'))[:300]}"
                        )

            if responses:
                lines.append("\nResponses:")
                for code, resp in responses.items():
                    if not isinstance(resp, dict):
                        continue
                    resp_desc = resp.get("description", "")
                    lines.append(f"  {code}: {resp_desc}")

            chunk_text = "\n".join(lines).strip()

            # --- Overflow detection ---
            oversize = len(chunk_text) > chunk_size
            # Never split — keep operation whole, just flag it

            chunks.append(ChunkRecord(
                content=chunk_text,
                metadata={
                    # Citation
                    "source":           str(source),
                    "filename":         Path(source).name if source != "unknown" else "unknown",
                    # Operation identity
                    "method":           method.lower(),
                    "path":             path,
                    "operation_id":     operation_id,
                    "summary":          summary,
                    "tags":             tags,                  # list[str]
                    "has_request_body": has_request_body,
                    "response_codes":   response_codes,        # list[str] — ?| filterable
                    # Position
                    "chunk_index":      op_index,
                    "chunk_total":      total_ops,
                    # Chunker
                    "strategy":         "openapi_operation",
                    "chunk_size":       chunk_size,
                    "oversize":         oversize,
                    "word_count":       len(chunk_text.split()),
                }
            ))

            op_index += 1

    return chunks


# ---------------------------------------------------------------------------
# Strategy 4: Semantic split  (STUB — requires embedder)
# For: long documents with topic shifts
# ---------------------------------------------------------------------------

def semantic_split(
    text:       str,
    source:     str | Path = "unknown",
    chunk_size: int = 1200,
) -> list[ChunkRecord]:
    """
    Split by embedding-similarity between adjacent sentence windows.
    A drop in cosine similarity signals a topic boundary — split there.

    STUB — implement after embedders.py is wired into the pipeline.

    Algorithm when ready:
      1. Split text into sentences (use the SENTENCE_END pattern from above)
      2. Embed each sentence (or a sliding window of 3 sentences)
      3. Compute cosine similarity between adjacent windows
      4. Where similarity < threshold (default ~0.5), start new chunk
      5. Merge small adjacent chunks up to chunk_size

    Why this is deferred:
      Calling an embedding model here creates a circular dependency —
      the chunker runs before the embedder in the pipeline. The simplest
      resolution: expose a chunker factory that accepts an embed_fn callable,
      injected when the embedder is available.

    Planned signature when implemented:
      semantic_split(text, source, chunk_size, embed_fn, threshold=0.5)
    """
    raise NotImplementedError(
        "semantic_split requires an embedding function. "
        "Implement after embedders.py is wired — see docstring for algorithm."
    )


# ---------------------------------------------------------------------------
# CHUNKER_REGISTRY — single dispatch table for the ingestion pipeline
# ---------------------------------------------------------------------------

# Type: takes (text, source, **kwargs) → list[ChunkRecord]
_ChunkerFn = _Callable[..., list[ChunkRecord]]

CHUNKER_REGISTRY: dict[str, _ChunkerFn | None] = {
    "txt":  recursive_split,       # prose, plain text, logs
    "md":   header_aware_split,    # markdown — headers are the structure
    "json": chunk_openapi_spec,    # OpenAPI / Swagger specs
    "pdf":  None,                  # Week 13 — Docling multimodal parser
    # Add as needed:
    # "yaml": chunk_openapi_spec,  # OpenAPI also ships as YAML — wire if needed
    # "rst":  recursive_split,     # reStructuredText — no header parser yet
}


def get_chunker(extension: str) -> _ChunkerFn:
    """
    Return the chunker function for a given file extension.

    Raises ValueError for unknown extensions.
    Raises NotImplementedError for known-but-unbuilt types (e.g. pdf).

    Why two different exceptions:
      ValueError  = caller passed something we've never heard of (bad input)
      NotImplementedError = we know about this type, it's on the roadmap
    """
    ext = extension.lower().lstrip(".")
    if ext not in CHUNKER_REGISTRY:
        supported = [f".{k}" for k, v in CHUNKER_REGISTRY.items() if v is not None]
        raise ValueError(
            f"No chunker registered for .{ext}. "
            f"Supported: {supported}"
        )
    chunker = CHUNKER_REGISTRY[ext]
    if chunker is None:
        raise NotImplementedError(
            f"Chunker for .{ext} is planned but not yet implemented. "
            f"See Week 13 (Docling multimodal ingestion)."
        )
    return chunker


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

_LAB_44_OPENAPI = """
{
  "openapi": "3.0.3",
  "info": {"title": "ai-platform", "version": "1.0.0"},
  "paths": {
    "/ingest": {
      "post": {
        "operationId": "ingestDocument",
        "summary": "Upload and ingest a document into the knowledge base",
        "tags": ["ingestion"],
        "parameters": [
          {
            "name": "namespace",
            "in": "query",
            "required": true,
            "description": "Target namespace for tenant isolation"
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "content":     {"type": "string"},
                  "document_id": {"type": "string"},
                  "file_type":   {"type": "string", "enum": ["txt","md","json"]}
                },
                "required": ["content", "document_id"]
              }
            }
          }
        },
        "responses": {
          "200": {"description": "Document ingested successfully"},
          "400": {"description": "Bad request — invalid payload"},
          "422": {"description": "Unprocessable entity — validation error"},
          "429": {"description": "Rate limit exceeded"}
        }
      }
    },
    "/search": {
      "post": {
        "operationId": "searchKnowledgeBase",
        "summary": "Hybrid search across the knowledge base",
        "tags": ["retrieval"],
        "parameters": [
          {
            "name": "namespace",
            "in": "query",
            "required": true,
            "description": "Namespace to search within"
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "query": {"type": "string"},
                  "top_k": {"type": "integer", "default": 10}
                },
                "required": ["query"]
              }
            }
          }
        },
        "responses": {
          "200": {"description": "Search results with citations"},
          "422": {"description": "Validation error"}
        }
      }
    },
    "/health": {
      "get": {
        "operationId": "healthCheck",
        "summary": "Platform health — DB, Redis, model availability",
        "tags": ["ops"],
        "responses": {
          "200": {"description": "All systems operational"},
          "503": {"description": "One or more dependencies unavailable"}
        }
      }
    }
  }
}
"""

# ---------------------------------------------------------------------------
# Benchmark chart
# ---------------------------------------------------------------------------

def _save_benchmark_chart(
    results: dict[str, tuple[float, int]],
    out_path: str = "benchmarks/lab_4.4_chunking_benchmarks.png",
) -> None:
    """
    Bar chart: chunks/sec per strategy.
    Saves to benchmarks/ alongside other lab PNGs.

    Args:
        results:  {label: (chunks_per_sec, chunk_count)}
        out_path: output path relative to project root
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    labels   = list(results.keys())
    cps_vals = [results[l][0] for l in labels]
    counts   = [results[l][1] for l in labels]

    fig, ax = plt.subplots(figsize=(8, 5))

    colors = ["#4C8BF5", "#34A853", "#FA7B17"]
    bars = ax.bar(labels, cps_vals, color=colors[:len(labels)], width=0.5, zorder=3)

    # Value labels on top of each bar
    for bar, cps, n in zip(bars, cps_vals, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(cps_vals) * 0.02,
            f"{cps:,.0f} c/s\n({n} chunks)",
            ha="center", va="bottom", fontsize=9, color="#333333",
        )

    ax.set_title("Lab 4.4 — Chunking Strategy Throughput", fontsize=13, pad=14)
    ax.set_ylabel("Chunks per second (higher = faster)", fontsize=10)
    ax.set_xlabel("Strategy", fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

    # Annotation explaining what each strategy is suited for
    notes = [
        "prose / .txt\ngeneral docs",
        "markdown\nREADMEs / wikis",
        "OpenAPI .json\none op per chunk",
    ]
    for bar, note in zip(bars, notes):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            max(cps_vals) * 0.04,
            note,
            ha="center", va="bottom", fontsize=7.5,
            color="white", fontweight="bold",
        )

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"\nChart saved → {out_path}")


if __name__ == "__main__":
    # --- Test 1: recursive_split ---
    print("=" * 60)
    print("TEST 1: recursive_split")
    print("=" * 60)

    sample_prose = """
Retrieval-augmented generation combines retrieval systems with generative models.
Instead of encoding all knowledge into model weights, RAG retrieves relevant
documents at inference time and provides them as context.

The retrieval component uses dense vector search. Each document is split into
chunks, embedded into a high-dimensional vector space, and stored in a vector
database. At query time, the query is embedded and nearest neighbors are retrieved.

Chunking strategy is one of the most impactful decisions in a RAG pipeline.
A chunk that cuts mid-sentence produces an embedding of an incomplete thought.
When retrieved, it provides partial context that can mislead the language model.

Recursive chunking tries paragraph boundaries first, then sentence boundaries,
then character boundaries. This hierarchy respects document structure at the
highest level possible given the size constraint.
    """.strip()

    chunks = recursive_split(sample_prose, source="docs/rag_overview.txt", chunk_size=300, overlap=50)
    print(f"Produced {len(chunks)} chunks\n")
    for c in chunks:
        print(c)
        print(f"  char_start={c.metadata['char_start']}  char_end={c.metadata['char_end']}  words={c.metadata['word_count']}")
    print()

    assert all(c.embedding is None for c in chunks)
    assert all("char_start" in c.metadata and "char_end" in c.metadata for c in chunks)
    assert all("word_count" in c.metadata for c in chunks)
    # Verify char positions are non-decreasing
    positions = [c.metadata["char_start"] for c in chunks]
    assert positions == sorted(positions), "char_start positions out of order"
    print("recursive_split assertions passed\n")

    # --- Test 2: header_aware_split ---
    print("=" * 60)
    print("TEST 2: header_aware_split")
    print("=" * 60)

    sample_md = """
# Overview

This platform handles production-grade AI document ingestion.
It solves memory, concurrency, and database bottlenecks at scale.

## Architecture

The system is built around three core concerns: memory efficiency,
async concurrency, and bulk database writes.

### Database Layer

We use PostgreSQL with pgvector. Connection pooling via asyncpg.
COPY-based bulk inserts achieve 102K rows/second.

### Ingestion Pipeline

Documents flow through: read → clean → chunk → embed → store.
Each stage is a generator to maintain O(1) memory usage.

## Deployment

Docker Compose for local development. The stack requires
PostgreSQL 15+ with the pgvector extension installed.
    """.strip()

    md_chunks = header_aware_split(sample_md, source="docs/architecture.md", chunk_size=400)
    print(f"Produced {len(md_chunks)} chunks\n")
    for c in md_chunks:
        print(c)
        print(f"  header_path: '{c.metadata['header_path']}'")
        print(f"  header_level: {c.metadata['header_level']}  section_index: {c.metadata['section_index']}")
        print()

    assert all(c.embedding is None for c in md_chunks)
    assert all("header_path" in c.metadata for c in md_chunks)
    assert all("header" in c.metadata for c in md_chunks)
    # header_path for a nested section should contain parent
    nested = [c for c in md_chunks if c.metadata["header_level"] == 3]
    assert all(" > " in c.metadata["header_path"] for c in nested), \
        "nested headers should have full path"
    print("header_aware_split assertions passed\n")

    # --- Test 3: chunk_openapi_spec ---
    print("=" * 60)
    print("TEST 3: chunk_openapi_spec")
    print("=" * 60)

    api_chunks = chunk_openapi_spec(
        _LAB_44_OPENAPI,
        source="docs/openapi.json",
        chunk_size=1200,
    )

    print(f"Produced {len(api_chunks)} operation chunks\n")
    for c in api_chunks:
        print(c)
        m = c.metadata
        print(f"  method={m['method'].upper()}  path={m['path']}")
        print(f"  operation_id={m['operation_id']}")
        print(f"  tags={m['tags']}")
        print(f"  has_request_body={m['has_request_body']}")
        print(f"  response_codes={m['response_codes']}")
        print(f"  oversize={m['oversize']}")
        print()

    # Assertions
    assert len(api_chunks) == 3, f"Expected 3 ops, got {len(api_chunks)}"
    assert all(c.embedding is None for c in api_chunks)

    # Every chunk has the required metadata fields
    required_fields = {
        "method", "path", "operation_id", "summary",
        "tags", "has_request_body", "response_codes", "oversize"
    }
    for c in api_chunks:
        missing = required_fields - c.metadata.keys()
        assert not missing, f"Missing metadata fields: {missing}"

    # response_codes must be list[str] — needed for PostgreSQL ?| operator
    for c in api_chunks:
        assert isinstance(c.metadata["response_codes"], list)
        assert all(isinstance(code, str) for code in c.metadata["response_codes"])

    # tags must be list
    for c in api_chunks:
        assert isinstance(c.metadata["tags"], list)

    # POST /ingest should have has_request_body=True
    ingest = next(c for c in api_chunks if c.metadata["path"] == "/ingest")
    assert ingest.metadata["has_request_body"] is True
    assert "429" in ingest.metadata["response_codes"]

    # GET /health should have has_request_body=False
    health = next(c for c in api_chunks if c.metadata["path"] == "/health")
    assert health.metadata["has_request_body"] is False

    print("chunk_openapi_spec assertions passed\n")

    # --- Test 4: get_chunker dispatch ---
    print("=" * 60)
    print("TEST 4: CHUNKER_REGISTRY + get_chunker")
    print("=" * 60)

    assert get_chunker("txt")  is recursive_split
    assert get_chunker(".md")  is header_aware_split   # leading dot stripped
    assert get_chunker("JSON") is chunk_openapi_spec   # case-insensitive
    print("Extension dispatch: txt ✓  md ✓  json ✓")

    try:
        get_chunker("pdf")
        assert False, "should have raised"
    except NotImplementedError as e:
        print(f"pdf → NotImplementedError ✓  ({e})")

    try:
        get_chunker("xlsx")
        assert False, "should have raised"
    except ValueError as e:
        print(f"xlsx → ValueError ✓  ({e})")

    # --- Benchmark 5: Strategy comparison ---
    print("=" * 60)
    print("BENCHMARK 5: chunks/sec per strategy")
    print("=" * 60)

    # Build a ~20KB prose doc by repeating sample_prose
    large_prose = (sample_prose + "\n\n") * 50        # ~20KB
    large_md    = (sample_md    + "\n\n") * 20        # ~20KB markdown
    RUNS = 10

    def _bench(fn, text, **kwargs) -> tuple[float, int]:
        """Run fn RUNS times, return (mean_chunks_per_sec, chunk_count)."""
        times = []
        count = 0
        for _ in range(RUNS):
            t0 = time.perf_counter()
            result = fn(text, source="bench", **kwargs)
            times.append(time.perf_counter() - t0)
            count = len(result)
        mean_sec = statistics.mean(times)
        return count / mean_sec, count

    strategies = {
        "recursive\n(txt)":      (_bench, recursive_split,    large_prose,     {}),
        "header_aware\n(md)":    (_bench, header_aware_split, large_md,        {}),
        "openapi\n(json)":       (_bench, chunk_openapi_spec, _LAB_44_OPENAPI, {}),
    }

    results: dict[str, tuple[float, int]] = {}
    for label, (bench_fn, strategy_fn, text, kwargs) in strategies.items():
        cps, n = bench_fn(strategy_fn, text, **kwargs)
        results[label] = (cps, n)
        print(f"  {label.replace(chr(10), ' '):<28}  {cps:>8.1f} chunks/sec   ({n} chunks per run)")

    _save_benchmark_chart(results)
    print("\nAll Lab 4.4 tests passed.")