"""Cache keys carry the tenant (requirement 11). Redis behaviour is covered in the integration tier."""
from uuid import uuid4

from api.services.cache import CACHE_SCHEMA_VERSION, cache_key

A, B = uuid4(), uuid4()


def test_same_tenant_same_inputs_gives_the_same_key_and_normalises_the_query():
    assert cache_key(A, "What is AI?", "legal", 5) == cache_key(A, "  what is ai?  ", "legal", 5)


def test_a_different_tenant_never_shares_a_key():
    assert cache_key(A, "q", "legal", 5) != cache_key(B, "q", "legal", 5)


def test_tenant_given_as_string_or_uuid_is_the_same_key():
    assert cache_key(A, "q", "legal", 5) == cache_key(str(A), "q", "legal", 5)


def test_every_other_part_still_changes_the_key():
    base = cache_key(A, "q", "legal", 5, "hybrid", True)
    assert base != cache_key(A, "q2", "legal", 5, "hybrid", True)
    assert base != cache_key(A, "q", "kyc_aml", 5, "hybrid", True)
    assert base != cache_key(A, "q", "legal", 6, "hybrid", True)
    assert base != cache_key(A, "q", "legal", 5, "bm25_only", True)
    assert base != cache_key(A, "q", "legal", 5, "hybrid", False)


def test_key_is_versioned_and_does_not_leak_the_tenant_or_the_query():
    key = cache_key(A, "secret question", "legal", 5)
    assert key.startswith(f"cache:v{CACHE_SCHEMA_VERSION}:")
    assert str(A) not in key and "secret" not in key


def test_schema_version_was_bumped_so_pre_tenant_entries_are_unreachable():
    assert CACHE_SCHEMA_VERSION >= 2
