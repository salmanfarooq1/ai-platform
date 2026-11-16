#!/usr/bin/env python3
"""Measure the real gateway and Postgres decision recorder with a no-op fake caller."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.pg_evidence import PgDecisionSink  # noqa: E402 - needs the sys.path line above
from core.identity.admin import admin_connection, create_principal, create_tenant  # noqa: E402
from core.identity.models import Principal  # noqa: E402
from gateway.boundary import build_boundary  # noqa: E402
from gateway.enforce import enforce  # noqa: E402
from gateway.policy import DEFAULT_POLICY  # noqa: E402
from gateway.types import Action, ActionKind, EnforcementContext, GatewayRuntime  # noqa: E402
from ports.models import ModelIdentity, ModelRoute, ModelUse, ResolvedModel  # noqa: E402
from tests import harness  # noqa: E402


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return ordered[index]


async def _fake_call() -> None:
    """Stand in for a model call without making provider I/O."""


async def _measure_mode(
    mode: str,
    iterations: int,
    concurrency: int,
    make_call: Callable[[], Awaitable[None]],
) -> None:
    samples: list[float] = []
    decision_count = iterations * concurrency
    started = time.perf_counter()

    async def one() -> None:
        baseline_start = time.perf_counter_ns()
        await _fake_call()
        baseline_ns = time.perf_counter_ns() - baseline_start
        decision_start = time.perf_counter_ns()
        await make_call()
        total_ns = time.perf_counter_ns() - decision_start
        samples.append(max(0.0, (total_ns - baseline_ns) / 1_000_000))

    if concurrency == 1:
        for _ in range(decision_count):
            await one()
    else:
        for _ in range(iterations):
            await asyncio.gather(*(one() for _ in range(concurrency)))

    elapsed = time.perf_counter() - started
    dps = decision_count / elapsed if elapsed else 0.0
    print(
        f"{mode}: decisions={decision_count} decisions_per_second={dps:.2f} "
        f"p50_added_ms={statistics.median(samples):.3f} "
        f"p95_added_ms={_percentile(samples, 0.95):.3f}"
    )


async def _run(iterations: int) -> None:
    harness.require_postgres()
    harness.ensure_app_role()
    database_name, owner_dsn = harness.create_database(prefix="gap_bench_")
    try:
        harness.migrate(owner_dsn)
        app_dsn = harness.app_url(owner_dsn)
        with admin_connection(owner_dsn) as conn:
            tenant_id = create_tenant(conn, "decision-path-bench", default_kb=False, deploy_shape="multi_tenant")
            principal_id = create_principal(conn, "decision-path-bench", "service", "benchmark")

        pool = await asyncpg.create_pool(dsn=app_dsn, min_size=1, max_size=32, statement_cache_size=0)
        try:
            principal = Principal(
                id=UUID(str(principal_id)), tenant_id=UUID(str(tenant_id)), kind="service",
                scopes=frozenset({"query"}),
            )
            runtime = GatewayRuntime(
                pool=pool, cache=object(), decisions=PgDecisionSink(pool),
                enabled_modules=frozenset({"gateway"}),
            )
            identity = ModelIdentity(
                alias="bench/fake", provider="fake", source="local", digest="sha256:" + "0" * 64,
                provider_model_id=None, processing_scope="local", region="local", storage_geography=None,
            )
            route = ModelRoute(identity=identity, endpoint="http://127.0.0.1/fake", credential=None, params={})
            resolved = ResolvedModel(
                identity=identity, route=route, use=ModelUse.CHAT, price_ref=None, data_use="no_training",
            )
            boundary = build_boundary(principal, DEFAULT_POLICY)
            counter = 0

            async def decision_call() -> None:
                nonlocal counter
                counter += 1
                ctx = EnforcementContext(
                    principal=principal, request_id=f"bench-{counter}", trace_id="decision-path-bench",
                    boundary=boundary, runtime=runtime,
                )
                decision = await enforce(
                    ctx,
                    Action(
                        kind=ActionKind.MODEL_INVOKE, resource=identity.alias,
                        resolved_model=resolved, model_phase="attempt",
                    ),
                )
                if not decision.allowed:
                    raise RuntimeError(f"benchmark decision was denied: {decision.reason}")

            await _measure_mode("serial", iterations, 1, decision_call)
            await _measure_mode("8-way", iterations, 8, decision_call)
            await _measure_mode("32-way", iterations, 32, decision_call)
        finally:
            await pool.close()
    finally:
        harness.drop_database(database_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=3, help="iterations per concurrent caller (default: 3)")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")
    try:
        asyncio.run(_run(args.iterations))
    except Exception as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
