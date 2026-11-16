"""Policy publication uses independent operator connections to a throwaway database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest

from core.identity.admin import admin_connection, create_tenant
from gateway import admin


@pytest.fixture
def policy_tenant(database_url):
    slug = "policy-cas-" + uuid4().hex[:12]
    with admin_connection(database_url) as conn:
        tenant_id = create_tenant(conn, slug, default_kb=False, deploy_shape="multi_tenant")
    return slug, str(tenant_id)


def history(database_url, tenant_id):
    with admin_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT version, document, created_by, created_at, active FROM policies WHERE tenant_id = %s ORDER BY version", (tenant_id,))
        return cur.fetchall()


def wait_for_lock(conn, backend_pid, *, timeout=10):
    """Fail unless Postgres observes this backend waiting for a lock."""
    deadline = monotonic() + timeout
    with conn.cursor() as cur:
        while True:
            cur.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (backend_pid,))
            if cur.fetchone() == ("Lock",):
                return
            assert monotonic() < deadline, "writer B did not wait on a Postgres lock"
            sleep(0.01)


def test_policy_cas_preserves_history_and_rejects_missing_head(database_url, policy_tenant):
    slug, tenant_id = policy_tenant
    with admin_connection(database_url) as conn:
        with pytest.raises(admin.PolicyConflict):
            admin.set_policy(conn, slug, {}, "stale", expected_version=1)
        assert admin.set_policy(conn, slug, {}, "first", expected_version=0) == 1
    before = history(database_url, tenant_id)
    with admin_connection(database_url) as conn:
        assert admin.set_policy(conn, slug, {"allowed_models": "*"}, "second", expected_version=1) == 2
    with admin_connection(database_url) as conn:
        with pytest.raises(admin.PolicyConflict):
            admin.set_policy(conn, slug, {}, "stale", expected_version=1)
    after = history(database_url, tenant_id)
    assert [row[0] for row in after] == [1, 2]
    assert before[0][:-1] == after[0][:-1]
    assert [row[-1] for row in after] == [False, True]


@pytest.mark.parametrize("initial", [False, True], ids=["first-publication", "existing-head"])
@pytest.mark.parametrize("cas", [False, True], ids=["unconditional", "compare-and-swap"])
def test_two_concurrent_policy_writers(database_url, policy_tenant, initial, cas):
    slug, tenant_id = policy_tenant
    if initial:
        with admin_connection(database_url) as conn:
            assert admin.set_policy(conn, slug, {}, "baseline") == 1
    before = history(database_url, tenant_id)
    started = Event()
    backend_pid = []

    def publish_b():
        try:
            with admin_connection(database_url) as conn:
                backend_pid.append(conn.get_backend_pid())
                started.set()
                return admin.set_policy(conn, slug, {"allowed_models": "*"}, "writer-b",
                                        expected_version=int(initial) if cas else None)
        except admin.PolicyConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin_connection(database_url) as conn_a:
            first = admin.set_policy(conn_a, slug, {"allowed_models": "*"}, "writer-a",
                                     expected_version=int(initial) if cas else None)
            future = pool.submit(publish_b)
            try:
                assert started.wait(timeout=10)
                # Autocommit gives every poll a fresh Postgres activity snapshot.
                with admin_connection(database_url) as observer:
                    observer.autocommit = True
                    wait_for_lock(observer, backend_pid[0])
                assert not future.done()
            finally:
                conn_a.commit()  # Release A even if the overlap assertion fails.
        results = [first, future.result(timeout=10)]
    assert results[0] == int(initial) + 1
    assert results[1] == ("conflict" if cas else int(initial) + 2)
    assert results.count("conflict") == (1 if cas else 0)
    versions = sorted(value for value in results if isinstance(value, int))
    assert versions == list(range(int(initial) + 1, int(initial) + 1 + (1 if cas else 2)))
    after = history(database_url, tenant_id)
    assert [row[0] for row in after] == list(range(1, len(after) + 1))
    assert sum(row[-1] for row in after) == 1
    assert [row[:-1] for row in before] == [row[:-1] for row in after[:len(before)]]
