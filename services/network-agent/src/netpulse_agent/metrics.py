"""Bounded Prometheus metrics for agent collection and delivery."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge

COLLECTOR_NAMES = frozenset(
    {
        "router_ping",
        "external_ping",
        "dns",
        "http",
        "wifi",
        "heartbeat",
        "speed_test",
    }
)
COLLECTION_OUTCOMES = frozenset({"succeeded", "failed"})
PUBLICATION_OUTCOMES = frozenset({"acknowledged", "failed"})


class AgentMetrics:
    """Record privacy-safe agent metrics with fixed-cardinality labels."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._collections = Counter(
            "netpulse_agent_collections_total",
            "Collector invocations by collector and outcome.",
            ("collector", "outcome"),
            registry=registry,
        )
        self._publications = Counter(
            "netpulse_agent_publications_total",
            "Outbox publication attempts by acknowledgement outcome.",
            ("outcome",),
            registry=registry,
        )
        self._outbox_depth = Gauge(
            "netpulse_agent_outbox_depth",
            "Current number of undelivered outbox records.",
            registry=registry,
        )
        self._oldest_pending_age = Gauge(
            "netpulse_agent_outbox_oldest_pending_age_seconds",
            "Age of the oldest undelivered outbox record, or zero when empty.",
            registry=registry,
        )
        self._last_collection_success = Gauge(
            "netpulse_agent_last_collection_success_timestamp_seconds",
            "Unix timestamp of the latest successful collector invocation.",
            registry=registry,
        )
        self._last_publication_success = Gauge(
            "netpulse_agent_last_publication_success_timestamp_seconds",
            "Unix timestamp of the latest acknowledged outbox publication.",
            registry=registry,
        )
        for collector in COLLECTOR_NAMES:
            for outcome in COLLECTION_OUTCOMES:
                self._collections.labels(collector=collector, outcome=outcome)
        for outcome in PUBLICATION_OUTCOMES:
            self._publications.labels(outcome=outcome)

    def record_collection(
        self,
        collector: str,
        outcome: str,
        timestamp_seconds: float | None = None,
    ) -> None:
        if collector not in COLLECTOR_NAMES:
            raise ValueError(f"unsupported collector: {collector}")
        if outcome not in COLLECTION_OUTCOMES:
            raise ValueError(f"unsupported collection outcome: {outcome}")
        self._collections.labels(collector=collector, outcome=outcome).inc()
        if outcome == "succeeded" and timestamp_seconds is not None:
            self._last_collection_success.set(timestamp_seconds)

    def record_publication(
        self,
        outcome: str,
        timestamp_seconds: float | None = None,
    ) -> None:
        if outcome not in PUBLICATION_OUTCOMES:
            raise ValueError(f"unsupported publication outcome: {outcome}")
        self._publications.labels(outcome=outcome).inc()
        if outcome == "acknowledged" and timestamp_seconds is not None:
            self._last_publication_success.set(timestamp_seconds)

    def set_outbox(self, depth: int, oldest_pending_age_seconds: float | None) -> None:
        self._outbox_depth.set(depth)
        self._oldest_pending_age.set(oldest_pending_age_seconds or 0.0)
