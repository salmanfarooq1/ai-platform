"""
core/processing/cpu_offload.py
================================
Shared ProcessPoolExecutor + async helper for offloading CPU-bound work
without blocking the event loop.

WHY THIS EXISTS:
  FastAPI (and asyncio in general) is single-threaded. If a coroutine calls
  a CPU-heavy function directly — chunking a 10MB doc, hashing a file — the
  event loop stalls. Every other in-flight request waits until that computation
  finishes. Under load this completely kills concurrency.

  run_cpu_bound() is the solution: it hands the callable to a process pool
  worker, returns control to the event loop immediately, and resumes the
  coroutine with the result when the process is done.

USAGE (from any async context):
  from core.processing.cpu_offload import run_cpu_bound
  from core.ingestion.chunkers import recursive_split

  chunks = await run_cpu_bound(recursive_split, text, source)

RULES FOR CALLABLES PASSED TO run_cpu_bound:
  1. Must be a plain function — not a coroutine, not a lambda, not a closure
     that captures unpicklable state. Process pool workers communicate via
     pickle; only picklable objects cross the boundary.
  2. Arguments must also be picklable (str, bytes, list, dict — all fine).
  3. Return value must be picklable (list[ChunkRecord] is fine — dataclass).
  4. Keep the payload small. Sending 100MB across processes costs more than
     the CPU work saves. Lab 4.2 found break-even at ~100KB for this workload.
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable

# One pool, shared for the entire process lifetime.
# Spawning is expensive (~50–150ms per worker on cold start).
# Creating a new pool per request would defeat the purpose.
_pool: ProcessPoolExecutor | None = None


def get_pool(max_workers: int = 4) -> ProcessPoolExecutor:
    """
    Return the shared ProcessPoolExecutor, creating it on first call.

    max_workers defaults to 4 — one per physical core on a standard 4-core
    machine. Override via the caller if the deployment target has more cores.
    Tuning rule: set max_workers = os.cpu_count() for CPU-only machines,
    or leave at 4 for mixed I/O + CPU workloads to avoid starving the event loop.

    Not thread-safe by design: called from the async event loop (single thread).
    If you need thread-safety, add a threading.Lock around the lazy init.
    """
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=max_workers)
    return _pool


def shutdown_pool() -> None:
    """
    Gracefully shut down the shared pool.

    Call this on application shutdown (FastAPI lifespan `shutdown` event)
    so worker processes exit cleanly instead of being killed by the OS.
    Not calling this means zombie processes on some platforms.
    """
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=True)
        _pool = None


async def run_cpu_bound(fn: Callable, *args: Any) -> Any:
    """
    Run a CPU-bound callable in the shared process pool.

    The event loop is NOT blocked — it hands the task to a worker process
    and awaits the Future asynchronously. Other coroutines keep running
    while the process works.

    Args:
        fn:    A plain (non-async) function. Must be picklable — defined at
               module top-level, not a lambda or nested closure.
        *args: Positional arguments passed to fn. Must be picklable.

    Returns:
        Whatever fn(*args) returns. Must be picklable.

    Raises:
        The exception fn raises, re-raised in the calling coroutine.
        concurrent.futures.process.BrokenProcessPool if a worker crashes —
        callers should catch this and reinitialise the pool or return 500.

    Example:
        from core.ingestion.chunkers import recursive_split
        chunks = await run_cpu_bound(recursive_split, text, "docs/readme.txt")
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_pool(), fn, *args)
