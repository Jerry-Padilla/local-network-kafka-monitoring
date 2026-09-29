from __future__ import annotations

import pytest
from netpulse_classifier.metrics import ClassifierMetrics
from prometheus_client import CollectorRegistry, generate_latest


def test_classifier_metrics_cover_cycles_transitions_backlog_and_duration() -> None:
    registry = CollectorRegistry()
    metrics = ClassifierMetrics(registry)

    metrics.record_evaluation("succeeded", duration_seconds=0.2, timestamp_seconds=100)
    metrics.record_evaluation("failed", duration_seconds=0.3)
    for status in ("candidate", "open", "ongoing", "recovering", "resolved"):
        metrics.record_transition(status)
    metrics.set_pending_publications(3)

    output = generate_latest(registry).decode()
    assert 'netpulse_classifier_evaluations_total{outcome="succeeded"} 1.0' in output
    assert 'netpulse_classifier_evaluations_total{outcome="failed"} 1.0' in output
    assert "netpulse_classifier_evaluation_duration_seconds_count 2.0" in output
    assert "netpulse_classifier_last_success_timestamp_seconds 100.0" in output
    assert "netpulse_classifier_pending_publications 3.0" in output
    for status in ("candidate", "open", "ongoing", "recovering", "resolved"):
        assert f'netpulse_classifier_transitions_total{{status="{status}"}} 1.0' in output


def test_classifier_publication_metrics_have_bounded_outcomes() -> None:
    registry = CollectorRegistry()
    metrics = ClassifierMetrics(registry)

    metrics.record_publication("acknowledged")
    metrics.record_publication("failed")

    output = generate_latest(registry).decode()
    assert 'netpulse_classifier_publications_total{outcome="acknowledged"} 1.0' in output
    assert 'netpulse_classifier_publications_total{outcome="failed"} 1.0' in output
    with pytest.raises(ValueError, match="publication outcome"):
        metrics.record_publication("broker error text")
