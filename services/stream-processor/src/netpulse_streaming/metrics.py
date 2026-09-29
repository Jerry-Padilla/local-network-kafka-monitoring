"""Bounded Prometheus metrics for Spark streaming micro-batches."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

QUERY_KINDS = frozenset({"metrics", "failures"})
BATCH_OUTCOMES = frozenset({"succeeded", "failed"})
ROW_KIND = {"metrics": "accepted", "failures": "rejected"}


class StreamingMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self._batches = Counter(
            "netpulse_streaming_batches_total",
            "Streaming micro-batches by query kind and outcome.",
            ("query_kind", "outcome"),
            registry=registry,
        )
        self._rows = Counter(
            "netpulse_streaming_rows_total",
            "Rows persisted by accepted or rejected classification.",
            ("row_kind",),
            registry=registry,
        )
        self._duration = Histogram(
            "netpulse_streaming_batch_duration_seconds",
            "Streaming micro-batch sink duration by query kind.",
            ("query_kind",),
            registry=registry,
        )
        self._last_success = Gauge(
            "netpulse_streaming_last_success_timestamp_seconds",
            "Unix timestamp of the latest successful micro-batch by query kind.",
            ("query_kind",),
            registry=registry,
        )
        for query_kind in QUERY_KINDS:
            for outcome in BATCH_OUTCOMES:
                self._batches.labels(query_kind=query_kind, outcome=outcome)
            self._duration.labels(query_kind=query_kind)
            self._last_success.labels(query_kind=query_kind)
        for row_kind in ROW_KIND.values():
            self._rows.labels(row_kind=row_kind)

    def record_batch(
        self,
        query_kind: str,
        outcome: str,
        rows: int,
        duration_seconds: float,
        timestamp_seconds: float | None = None,
    ) -> None:
        if query_kind not in QUERY_KINDS:
            raise ValueError(f"unsupported query kind: {query_kind}")
        if outcome not in BATCH_OUTCOMES:
            raise ValueError(f"unsupported batch outcome: {outcome}")
        self._batches.labels(query_kind=query_kind, outcome=outcome).inc()
        self._rows.labels(row_kind=ROW_KIND[query_kind]).inc(rows)
        self._duration.labels(query_kind=query_kind).observe(duration_seconds)
        if outcome == "succeeded" and timestamp_seconds is not None:
            self._last_success.labels(query_kind=query_kind).set(timestamp_seconds)
