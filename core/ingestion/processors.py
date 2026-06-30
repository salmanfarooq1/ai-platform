"""
core/ingestion/processors.py
DEPRECATED — learning artifact.

The clean_chunks() function strips all non-alphanumeric characters, which
destroys meaningful punctuation, URLs, code snippets, and markdown formatting.

Production text processing is now handled by the chunking strategies in
core/ingestion/chunkers.py, which preserve document structure while splitting.

This file is kept for reference (it shows the generator pattern).
Do NOT use in production pipelines — use chunkers.py instead.
"""

import warnings

def clean_chunks(chunk_stream):
    """DEPRECATED: Use core.ingestion.chunkers instead. Strips all non-alphanumeric chars."""
    warnings.warn(
        "clean_chunks() is deprecated. Use chunkers.py strategies instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    for chunk in chunk_stream:
        cleaned = ''.join(c for c in chunk if c.isalnum() or c.isspace())
        if cleaned.strip():
            yield cleaned