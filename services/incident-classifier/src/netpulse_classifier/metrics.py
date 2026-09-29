"""Bounded Prometheus metrics for incident classification."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

EVALUATION_OUTCOMES = frozenset({"succeeded", "failed"})
TRANSITION_STATUSES = frozenset({"candidate", "open", "ongoing", "recovering", "resolved"})
PUBLICATION_OUTCOMES = frozenset({"acknowledged", "failed"})


class ClassifierMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self._evaluations = Counter(
            "netpulse_classifier_evaluations_total",
            "Classifier evaluation cycles by outcome.",
            ("outcome",),
            registry=registry,
        )
        self._transitions = Counter(
            "netpulse_classifier_transitions_total",
            "Durably persisted incident transitions by status.",
            ("status",),
            registry=registry,
        )
        self._publications = Counter(
            "netpulse_classifier_publications_total",
            "Incident outbox publications by outcome.",
            ("outcome",),
            registry=registry,
        )
        self._pending_publications = Gauge(
            "netpulse_classifier_pending_publications",
            "Current unpublished incident outbox records.",
            registry=registry,
        )
        self._duration = Histogram(
            "netpulse_classifier_evaluation_duration_seconds",
            "Classifier evaluation cycle duration.",
            registry=registry,
        )
        self._last_success = Gauge(
            "netpulse_classifier_last_success_timestamp_seconds",
            "Unix timestamp of the latest successful evaluation cycle.",
            registry=registry,
        )
        for outcome in EVALUATION_OUTCOMES:
            self._evaluations.labels(outcome=outcome)
        for status in TRANSITION_STATUSES:
            self._transitions.labels(status=status)
        for outcome in PUBLICATION_OUTCOMES:
            self._publications.labels(outcome=outcome)

    def record_evaluation(
        self,
        outcome: str,
        duration_seconds: float,
        timestamp_seconds: float | None = None,
    ) -> None:
        if outcome not in EVALUATION_OUTCOMES:
            raise ValueError(f"unsupported evaluation outcome: {outcome}")
        self._evaluations.labels(outcome=outcome).inc()
        self._duration.observe(duration_seconds)
        if outcome == "succeeded" and timestamp_seconds is not None:
            self._last_success.set(timestamp_seconds)

    def record_transition(self, status: str) -> None:
        if status not in TRANSITION_STATUSES:
            raise ValueError(f"unsupported transition status: {status}")
        self._transitions.labels(status=status).inc()

    def record_publication(self, outcome: str) -> None:
        if outcome not in PUBLICATION_OUTCOMES:
            raise ValueError(f"unsupported publication outcome: {outcome}")
        self._publications.labels(outcome=outcome).inc()

    def set_pending_publications(self, count: int) -> None:
        self._pending_publications.set(count)
