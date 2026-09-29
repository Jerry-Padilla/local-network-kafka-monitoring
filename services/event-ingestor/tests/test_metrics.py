from __future__ import annotations

import pytest
from netpulse_ingestion.metrics import IngestionMetrics
from prometheus_client import CollectorRegistry, generate_latest


def _samples(registry: CollectorRegistry) -> str:
    return generate_latest(registry).decode("utf-8")


def test_ingestion_metrics_expose_bounded_processing_outcomes() -> None:
    registry = CollectorRegistry()
    metrics = IngestionMetrics(registry)

    for outcome in ("valid", "duplicate", "dead_lettered", "failed"):
        metrics.record_processing(outcome, duration_seconds=0.25)

    output = _samples(registry)
    for outcome in ("valid", "duplicate", "dead_lettered", "failed"):
        assert f'netpulse_ingestion_records_total{{outcome="{outcome}"}} 1.0' in output
    assert "netpulse_ingestion_processing_duration_seconds_count 4.0" in output


def test_ingestion_metrics_track_retries_publication_and_last_success() -> None:
    registry = CollectorRegistry()
    metrics = IngestionMetrics(registry)

    metrics.record_retry()
    metrics.record_publication("acknowledged")
    metrics.record_publication("failed")
    metrics.mark_success(1_750_000_000.0)

    output = _samples(registry)
    assert "netpulse_ingestion_retries_total 1.0" in output
    assert 'netpulse_ingestion_publications_total{outcome="acknowledged"} 1.0' in output
    assert 'netpulse_ingestion_publications_total{outcome="failed"} 1.0' in output
    assert "netpulse_ingestion_last_success_timestamp_seconds 1.75e+09" in output


@pytest.mark.parametrize("outcome", ["unknown", "event-id", "database unavailable"])
def test_ingestion_metrics_reject_unbounded_label_values(outcome: str) -> None:
    metrics = IngestionMetrics(CollectorRegistry())

    with pytest.raises(ValueError, match="processing outcome"):
        metrics.record_processing(outcome, duration_seconds=0.1)

    with pytest.raises(ValueError, match="publication outcome"):
        metrics.record_publication(outcome)
