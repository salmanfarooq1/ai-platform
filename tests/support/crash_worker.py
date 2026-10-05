"""A worker process for the crash test: it claims a job, says so, and never finishes. The test kills it with SIGKILL.

    python -m tests.support.crash_worker <database url>
"""
import asyncio
import sys

import asyncpg

from workers.loop import Worker


async def never_finishes(job, ctx):
    print(f"RUNNING {job.id}", flush=True)
    await asyncio.sleep(3600)


async def main(dsn: str) -> None:
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3, statement_cache_size=0)
    await Worker(pool, {"ingest": never_finishes}, name="doomed", lease_seconds=2, poll_interval=0.05, beat_interval=0.2).run(1)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
