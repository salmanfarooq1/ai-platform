"""Scratch-only diagnostics for intermittent gateway decision ordering."""
import json
import sys


def _wrap(module, name, label):
    original = getattr(module, name)

    async def diagnostic(*args, **kwargs):
        result = await original(*args, **kwargs)
        print(label + "=" + json.dumps([
            {
                "action": row["action"],
                "outcome": row["outcome"],
                "reason": row["reason"],
                "created_at": row["created_at"].isoformat(),
                "chain_position": row.get("chain_position"),
            }
            for row in result
        ], sort_keys=True))
        return result

    setattr(module, name, diagnostic)


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        if item.name == "test_m4_the_scope_map_grants_feedback_to_query_and_analytics_to_kb_read":
            _wrap(sys.modules[item.module.__name__], "rows", "GATEWAY_ROWS_DIAGNOSTIC")
        elif item.name == "test_a2_every_decision_the_run_caused_carries_its_execution_id_including_the_ones_made_over_http_from_the_sandbox":
            _wrap(sys.modules[item.module.__name__], "decisions_of", "SANDBOX_DECISIONS_DIAGNOSTIC")
        elif item.name == "test_purge_jobs_are_not_shown_by_the_job_routes":
            module = sys.modules[item.module.__name__]
            original = module.run_purges

            async def purge_diagnostic(app_pool, *args, **kwargs):
                try:
                    return await original(app_pool, *args, **kwargs)
                except AssertionError:
                    try:
                        async with app_pool.acquire() as conn:
                            rows = await conn.fetch(
                                "SELECT id, status, attempts, max_attempts, run_after, lease_until, locked_by, "
                                "error_code, progress_done, progress_total, created_at, updated_at, started_at, "
                                "finished_at FROM jobs WHERE kind = 'purge_decisions' ORDER BY created_at DESC LIMIT 10"
                            )
                        import datetime

                        print("PURGE_TIMEOUT_JOBS_DIAGNOSTIC=" + json.dumps([
                            {
                                key: value.isoformat() if isinstance(value, datetime.datetime) else value
                                for key, value in dict(row).items()
                            }
                            for row in rows
                        ], default=str, sort_keys=True))
                    except Exception as diagnostic_error:
                        print("PURGE_TIMEOUT_DIAGNOSTIC_ERROR=" + type(diagnostic_error).__name__)
                    raise

            module.run_purges = purge_diagnostic
