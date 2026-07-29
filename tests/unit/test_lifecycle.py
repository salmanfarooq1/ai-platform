"""
tests/unit/test_lifecycle.py

Tests for the document lifecycle module (pure functions only).
"""
from core.ingestion.lifecycle import compute_content_hash


def test_hash_deterministic():
    """Same bytes must always produce the same hash."""
    content = b"GDPR compliance policy v1.0 effective 2025-01-01"
    assert compute_content_hash(content) == compute_content_hash(content)


def test_hash_different_content():
    """Different content must produce different hashes."""
    v1 = compute_content_hash(b"GDPR compliance policy v1.0")
    v2 = compute_content_hash(b"GDPR compliance policy v2.0")
    assert v1 != v2


def test_hash_is_64_hex_chars():
    """SHA-256 always produces a 64-character hex string."""
    result = compute_content_hash(b"test content")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_hash_empty_bytes():
    """Empty input should still produce a valid hash (SHA-256 of empty string)."""
    result = compute_content_hash(b"")
    assert len(result) == 64
    assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_hash_unicode_content():
    """Real compliance documents contain accented characters, curly quotes, etc."""
    content = "GDPR – règlement général sur la protection des données".encode("utf-8")
    assert compute_content_hash(content) == compute_content_hash(content)
    assert len(compute_content_hash(content)) == 64


def test_hash_large_content():
    """Ingested PDFs can be several MB; hashing shouldn't choke or truncate on size."""
    content = b"x" * (5 * 1024 * 1024)  # 5 MB
    result = compute_content_hash(content)
    assert len(result) == 64
