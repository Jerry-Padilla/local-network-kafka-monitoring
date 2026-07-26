from __future__ import annotations

from pathlib import Path

import pytest
from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.config import OutboxConfig
from netpulse_agent.events import EventFactory
from netpulse_agent.outbox import OutboxFullError, SQLiteOutbox
from netpulse_contracts.models import Event


def test_enqueue_is_deduplicated_and_sequence_persists(
    outbox: SQLiteOutbox,
    measurement_event: Event,
) -> None:
    assert outbox.enqueue(measurement_event, now=100) is True
    assert outbox.enqueue(measurement_event, now=100) is False
    assert outbox.depth() == 1
    assert outbox.next_sequence() == 1


def test_failure_backoff_delivery_and_acknowledged_pruning(
    outbox: SQLiteOutbox,
    measurement_event: Event,
) -> None:
    outbox.enqueue(measurement_event, now=100)
    record = outbox.ready(now=100)[0]

    next_attempt = outbox.mark_failed(record, "offline", now=100, random_value=0)

    assert next_attempt == 102
    assert outbox.ready(now=101) == []
    retried = outbox.ready(now=102)[0]
    assert retried.retry_count == 1

    outbox.mark_delivered(retried.event_id, now=110)
    assert outbox.depth() == 0
    assert outbox.stats().delivered_retained == 1
    assert outbox.prune_acknowledged(now=114) == 0
    assert outbox.prune_acknowledged(now=115) == 1


def test_storage_ceiling_rejects_new_event_without_deleting_pending(
    tmp_path: Path,
    event_factory: EventFactory,
) -> None:
    outbox = SQLiteOutbox(
        OutboxConfig(
            path=tmp_path / "small.db",
            maximum_bytes=1_048_576,
        )
    )
    oversized = event_factory.build(
        CollectedEvent(
            "network.measurement",
            {
                "measurement_type": "external_ping",
                "target_id": "probe",
                "success": True,
                "latency_ms": 1,
                "packet_loss_pct": 0,
                "future_blob": "x" * 1_100_000,
            },
        )
    )

    with pytest.raises(OutboxFullError):
        outbox.enqueue(oversized)

    assert outbox.depth() == 0
