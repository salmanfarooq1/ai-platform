"""Process metrics: OpenTelemetry instruments exported in the Prometheus text format (Sprint 008).

One `Metrics` object per process (`get_metrics()`), with its own registry so it never mixes with another library's
series. The series:

- `http_requests_total` and `http_request_duration_seconds`: labels `route` (the route template, never the raw
  path), `method`, `status`.
- `gateway_decisions_total`: labels `action`, `outcome`, `stage`. Counted in the process that recorded the decision,
  so the API and a worker each serve their own count.
- `jobs_total`: labels `kind`, `status`. The number of jobs now in each status, across tenants, read from Postgres
  at scrape time through a narrow SECURITY DEFINER function (counts only).
- `outbox_lag_seconds`: the age of the oldest unpublished outbox event, 0 when there is none, read the same way.

No label ever holds a tenant id, a principal id, a request id or any input text.
"""
import logging
from collections.abc import Iterable
from typing import Any

from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from prometheus_client import CollectorRegistry, generate_latest

logger = logging.getLogger("core.metrics")

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
JOB_KINDS = ("ingest", "agent_run", "purge_decisions")
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "dead")
_DURATION_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        reader = PrometheusMetricReader(disable_target_info=True, scope_info_enabled=False, registry=self.registry)
        self._provider = MeterProvider(metric_readers=[reader], resource=Resource.create({}))
        meter = self._provider.get_meter("ai-platform")
        self._requests = meter.create_counter("http_requests_total", description="HTTP requests by route, method and status")
        self._duration = meter.create_histogram(
            "http_request_duration_seconds", unit="s", description="HTTP request latency by route, method and status",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
        )
        self._decisions = meter.create_counter(
            "gateway_decisions_total", description="Gateway decisions by action, outcome and stage",
        )
        # The two database-backed series are read from this snapshot, which `set_database_snapshot` replaces.
        self._jobs: dict[tuple[str, str], int] = {}
        self._outbox_lag = 0.0
        meter.create_observable_gauge(
            "jobs_total", callbacks=[self._observe_jobs], description="Jobs now in each status, by kind",
        )
        meter.create_observable_gauge(
            "outbox_lag_seconds", callbacks=[self._observe_outbox_lag], unit="s",
            description="Age of the oldest unpublished outbox event (0 when none)",
        )

    # ------------------------------------------------------------------ recording

    def observe_request(self, route: str, method: str, status: int, seconds: float) -> None:
        attributes = {"route": route, "method": method, "status": str(status)}
        self._requests.add(1, attributes)
        self._duration.record(seconds, attributes)

    def count_decision(self, action: str, outcome: str, stage: str) -> None:
        self._decisions.add(1, {"action": action, "outcome": outcome, "stage": stage})

    def set_database_snapshot(self, jobs: Iterable[tuple[str, str, int]], outbox_lag_seconds: float) -> None:
        self._jobs = {(kind, status): int(count) for kind, status, count in jobs}
        self._outbox_lag = float(outbox_lag_seconds)

    # ------------------------------------------------------------------ callbacks

    def _observe_jobs(self, options: CallbackOptions) -> Iterable[Observation]:
        counts = {(kind, status): 0 for kind in JOB_KINDS for status in JOB_STATUSES}  # every series exists, at 0 when empty
        counts.update(self._jobs)
        return [Observation(count, {"kind": kind, "status": status}) for (kind, status), count in sorted(counts.items())]

    def _observe_outbox_lag(self, options: CallbackOptions) -> Iterable[Observation]:
        return [Observation(self._outbox_lag)]

    # ------------------------------------------------------------------ output

    async def refresh_from_database(self, pool: Any) -> None:
        """Read the job counts and the outbox lag. A database error keeps the last snapshot and is logged."""
        try:
            rows = await pool.fetch("SELECT job_kind, job_status, job_count FROM trust_jobs_by_status()")
            lag = await pool.fetchval("SELECT trust_outbox_lag()")
        except Exception:
            logger.warning("job and outbox metrics not refreshed", exc_info=True)
            return
        self.set_database_snapshot(((r["job_kind"], r["job_status"], r["job_count"]) for r in rows), float(lag or 0.0))

    def render(self) -> bytes:
        return generate_latest(self.registry)


_metrics: Metrics | None = None


def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics
