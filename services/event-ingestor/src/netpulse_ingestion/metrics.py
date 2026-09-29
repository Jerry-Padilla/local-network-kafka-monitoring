"""Bounded Prometheus metrics for the event-ingestion workflow."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

PROCESSING_OUTCOMES = frozenset({"valid", "duplicate", "dead_lettered", "failed"})
PUBLICATION_OUTCOMES = frozenset({"acknowledged", "failed"})


class IngestionMetrics:
    """Record ingestion signals without event-specific or error-text labels."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._records = Counter(
            "netpulse_ingestion_records_total",
            "Ingested source records by bounded processing outcome.",
            ("outcome",),
            registry=registry,
        )
        self._retries = Counter(
            "netpulse_ingestion_retries_total",
            "Source-record processing retries before backoff.",
            registry=registry,
        )
        self._publications = Counter(
            "netpulse_ingestion_publications_total",
            "Required downstream publications by acknowledgement outcome.",
            ("outcome",),
            registry=registry,
        )
        self._processing_duration = Histogram(
            "netpulse_ingestion_processing_duration_seconds",
            "End-to-end source-record processing duration.",
            registry=registry,
        )
        self._last_success = Gauge(
            "netpulse_ingestion_last_success_timestamp_seconds",
            "Unix timestamp of the latest durably processed source record.",
            registry=registry,
        )
        for outcome in PROCESSING_OUTCOMES:
            self._records.labels(outcome=outcome)
        for outcome in PUBLICATION_OUTCOMES:
            self._publications.labels(outcome=outcome)

    def record_processing(self, outcome: str, duration_seconds: float) -> None:
        if outcome not in PROCESSING_OUTCOMES:
            raise ValueError(f"unsupported processing outcome: {outcome}")
        self._records.labels(outcome=outcome).inc()
        self._processing_duration.observe(duration_seconds)

    def record_retry(self) -> None:
        self._retries.inc()

    def record_publication(self, outcome: str) -> None:
        if outcome not in PUBLICATION_OUTCOMES:
            raise ValueError(f"unsupported publication outcome: {outcome}")
        self._publications.labels(outcome=outcome).inc()

    def mark_success(self, timestamp_seconds: float) -> None:
        self._last_success.set(timestamp_seconds)
