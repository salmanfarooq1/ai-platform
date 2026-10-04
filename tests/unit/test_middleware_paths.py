"""Rate limit and budget (gateway stages since Sprint 004) watch the /v1 paths. API versioning constants."""
import pytest

from api.versioning import API_PREFIX, UNVERSIONED_PATHS
from gateway.limits import BUDGETED_PATHS as _BUDGETED_PATHS
from gateway.limits import LIMITED_PATHS as _LIMITED_PATHS

pytestmark = pytest.mark.unit


def test_prefix_and_unversioned_paths():
    assert API_PREFIX == "/v1"
    assert UNVERSIONED_PATHS == ("/", "/health")


def test_rate_limit_covers_the_expensive_v1_routes_only():
    assert _LIMITED_PATHS == ("/v1/search", "/v1/ingest", "/v1/agent/query", "/v1/mcp/sse")
    assert "/search" not in _LIMITED_PATHS


def test_token_budget_covers_the_llm_v1_routes_only():
    assert _BUDGETED_PATHS == ("/v1/search", "/v1/agent/query")
