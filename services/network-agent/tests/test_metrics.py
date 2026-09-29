from __future__ import annotations

import pytest
from netpulse_agent.metrics import AgentMetrics
from prometheus_client import CollectorRegistry, generate_latest


def _output(registry: CollectorRegistry) -> str:
    return generate_latest(registry).decode("utf-8")


def test_agent_metrics_use_only_fixed_collector_and_outcome_labels() -> None:
    registry = CollectorRegistry()
    metrics = AgentMetrics(registry)

    metrics.record_collection("router_ping", "succeeded", timestamp_seconds=100)
    metrics.record_collection("dns", "failed")

    output = _output(registry)
    assert (
        'netpulse_agent_collections_total{collector="router_ping",outcome="succeeded"} 1.0'
        in output
    )
    assert 'netpulse_agent_collections_total{collector="dns",outcome="failed"} 1.0' in output
    assert "netpulse_agent_last_collection_success_timestamp_seconds 100.0" in output

    with pytest.raises(ValueError, match="collector"):
        metrics.record_collection("user-supplied-target", "succeeded")
    with pytest.raises(ValueError, match="outcome"):
        metrics.record_collection("dns", "timeout from 192.0.2.1")


def test_agent_metrics_track_publication_and_queue_state() -> None:
    registry = CollectorRegistry()
    metrics = AgentMetrics(registry)

    metrics.record_publication("acknowledged", timestamp_seconds=200)
    metrics.record_publication("failed")
    metrics.set_outbox(depth=3, oldest_pending_age_seconds=42.5)

    output = _output(registry)
    assert 'netpulse_agent_publications_total{outcome="acknowledged"} 1.0' in output
    assert 'netpulse_agent_publications_total{outcome="failed"} 1.0' in output
    assert "netpulse_agent_outbox_depth 3.0" in output
    assert "netpulse_agent_outbox_oldest_pending_age_seconds 42.5" in output
    assert "netpulse_agent_last_publication_success_timestamp_seconds 200.0" in output

    with pytest.raises(ValueError, match="publication outcome"):
        metrics.record_publication("broker unavailable")
