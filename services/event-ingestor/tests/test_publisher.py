from __future__ import annotations

import pytest
from netpulse_ingestion.metrics import IngestionMetrics
from netpulse_ingestion.publisher import (
    KafkaPublicationError,
    SynchronousKafkaPublisher,
)
from prometheus_client import CollectorRegistry, generate_latest


class FakeProducer:
    callback_error = None
    invoke_callback = True

    def __init__(self, config) -> None:
        self.config = config

    def produce(self, **kwargs) -> None:
        if self.invoke_callback:
            kwargs["on_delivery"](self.callback_error, object())

    def poll(self, _timeout: float) -> int:
        return 0

    def flush(self, _timeout: float) -> int:
        return 0


def publisher(
    monkeypatch, metrics: IngestionMetrics | None = None
) -> SynchronousKafkaPublisher:
    monkeypatch.setattr("netpulse_ingestion.publisher.Producer", FakeProducer)
    return SynchronousKafkaPublisher(
        "broker:9092",
        "test",
        0.1,
        metrics or IngestionMetrics(CollectorRegistry()),
    )


def test_required_output_waits_for_successful_ack(monkeypatch) -> None:
    FakeProducer.callback_error = None
    FakeProducer.invoke_callback = True
    instance = publisher(monkeypatch)

    instance.publish("output", "agent", b"{}")
    instance.close()


def test_publication_acknowledgement_is_recorded(monkeypatch) -> None:
    FakeProducer.callback_error = None
    FakeProducer.invoke_callback = True
    registry = CollectorRegistry()
    instance = publisher(monkeypatch, IngestionMetrics(registry))

    instance.publish("output", "agent", b"{}")

    output = generate_latest(registry).decode()
    assert 'netpulse_ingestion_publications_total{outcome="acknowledged"} 1.0' in output


def test_delivery_error_is_propagated(monkeypatch) -> None:
    FakeProducer.callback_error = "broker rejected record"
    FakeProducer.invoke_callback = True
    instance = publisher(monkeypatch)

    with pytest.raises(KafkaPublicationError, match="broker rejected"):
        instance.publish("output", "agent", b"{}")


def test_publication_failure_is_recorded_once(monkeypatch) -> None:
    FakeProducer.callback_error = "broker rejected record"
    FakeProducer.invoke_callback = True
    registry = CollectorRegistry()
    instance = publisher(monkeypatch, IngestionMetrics(registry))

    with pytest.raises(KafkaPublicationError):
        instance.publish("output", "agent", b"{}")

    output = generate_latest(registry).decode()
    assert 'netpulse_ingestion_publications_total{outcome="failed"} 1.0' in output


def test_delivery_timeout_is_not_silently_ignored(monkeypatch) -> None:
    FakeProducer.callback_error = None
    FakeProducer.invoke_callback = False
    instance = publisher(monkeypatch)
    ticks = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr("netpulse_ingestion.publisher.time.monotonic", lambda: next(ticks))

    with pytest.raises(KafkaPublicationError, match="timed out"):
        instance.publish("output", "agent", b"{}")
