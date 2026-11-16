"""Restore a journey policy only while its version remains the active head."""

from typing import Any

from gateway.admin import PolicyConflict, set_policy


def restore_policy(conn: Any, tenant_slug: str, journey_version: int, baseline: dict[str, Any]) -> int | None:
    try:
        return set_policy(conn, tenant_slug, baseline, "showcase-restore", expected_version=journey_version)
    except PolicyConflict:
        print("WARN policy restore: head changed; no policy was overwritten")
        return None
