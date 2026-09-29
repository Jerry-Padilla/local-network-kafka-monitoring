from __future__ import annotations

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.events import EventFactory
from netpulse_agent.metrics import AgentMetrics
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_agent.scheduler import CollectionErrorTracker, CollectorWorker
from prometheus_client import CollectorRegistry, generate_latest


class FailingCollector:
    name = "dns"
    interval_seconds = 1.0

    def collect(self) -> list[CollectedEvent]:
        raise RuntimeError("sensitive details are not copied")


class SuccessfulCollector:
    name = "external_ping"
    interval_seconds = 1.0

    def collect(self) -> list[CollectedEvent]:
        return [
            CollectedEvent(
                "network.measurement",
                {
                    "measurement_type": "external_ping",
                    "target_id": "probe-a",
                    "success": True,
                    "latency_ms": 12.5,
                    "packet_loss_pct": 0.0,
                },
            )
        ]


def test_collector_failure_is_sanitized_and_does_not_escape(
    event_factory: EventFactory,
    outbox: SQLiteOutbox,
) -> None:
    errors = CollectionErrorTracker()
    registry = CollectorRegistry()
    worker = CollectorWorker(
        FailingCollector(),
        event_factory,
        outbox,
        errors,
        AgentMetrics(registry),
    )

    assert worker.collect_once() == 0
    assert len(errors.snapshot()) == 1
    assert errors.snapshot()[0].endswith("dns: RuntimeError")
    assert outbox.depth() == 0
    output = generate_latest(registry).decode()
    assert 'netpulse_agent_collections_total{collector="dns",outcome="failed"} 1.0' in output


def test_successful_collection_updates_success_and_outbox_metrics(
    event_factory: EventFactory,
    outbox: SQLiteOutbox,
) -> None:
    registry = CollectorRegistry()
    worker = CollectorWorker(
        SuccessfulCollector(),
        event_factory,
        outbox,
        CollectionErrorTracker(),
        AgentMetrics(registry),
    )

    assert worker.collect_once() == 1

    output = generate_latest(registry).decode()
    assert (
        'netpulse_agent_collections_total{collector="external_ping",outcome="succeeded"} 1.0'
        in output
    )
    assert "netpulse_agent_outbox_depth 1.0" in output
    assert "netpulse_agent_last_collection_success_timestamp_seconds" in output
