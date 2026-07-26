from __future__ import annotations

from typing import Any

from netpulse_agent.config import KafkaConfig
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_agent.publisher import DeliveryCallback, OutboxPublisher
from netpulse_contracts.models import Event


class FakeProducer:
    def __init__(self, error: Any = None) -> None:
        self.error = error
        self.callback: DeliveryCallback | None = None

    def produce(
        self,
        topic: str,
        value: bytes,
        key: str,
        on_delivery: DeliveryCallback,
    ) -> None:
        self.callback = on_delivery

    def poll(self, timeout: float) -> int:
        assert self.callback is not None
        callback = self.callback
        self.callback = None
        callback(self.error, None)  # type: ignore[arg-type]
        return 1

    def flush(self, timeout: float) -> int:
        return 0


def test_acknowledgement_marks_event_delivered(
    outbox: SQLiteOutbox,
    measurement_event: Event,
) -> None:
    outbox.enqueue(measurement_event)
    publisher = OutboxPublisher(
        KafkaConfig(delivery_timeout_seconds=1),
        outbox,
        producer=FakeProducer(),
    )

    assert publisher.publish_ready() == (1, 0)
    assert outbox.depth() == 0


def test_delivery_failure_preserves_event_for_retry(
    outbox: SQLiteOutbox,
    measurement_event: Event,
) -> None:
    outbox.enqueue(measurement_event, now=0)
    publisher = OutboxPublisher(
        KafkaConfig(delivery_timeout_seconds=1),
        outbox,
        producer=FakeProducer(error="broker unavailable"),
    )

    assert publisher.publish_ready() == (0, 1)
    assert outbox.depth() == 1
    assert outbox.stats().delivered_retained == 0
