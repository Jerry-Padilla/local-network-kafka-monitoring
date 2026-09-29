from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest
from netpulse_ingestion.config import IngestionConfig
from netpulse_ingestion.consumer import IngestionConsumer
from netpulse_ingestion.metrics import IngestionMetrics
from netpulse_ingestion.processor import ProcessingOutcome, ProcessingResult
from prometheus_client import CollectorRegistry, generate_latest


@dataclass
class FakeKafkaError:
    error_code: int

    def code(self) -> int:
        return self.error_code


class FakeMessage:
    def __init__(self, value: bytes = b"{}", error=None) -> None:
        self._value = value
        self._error = error

    def topic(self) -> str:
        return "network.measurements.raw.v1"

    def partition(self) -> int:
        return 1

    def offset(self) -> int:
        return 12

    def key(self) -> bytes:
        return b"network-agent-wifi-01"

    def value(self) -> bytes:
        return self._value

    def error(self):
        return self._error


class FakeKafkaConsumer:
    latest: ClassVar[FakeKafkaConsumer | None] = None
    queued_messages: ClassVar[list[FakeMessage]] = []

    def __init__(self, config) -> None:
        self.config = config
        self.messages = list(self.queued_messages)
        self.calls: list[str] = []
        self.stop = lambda: None
        type(self).latest = self

    def subscribe(self, topics, on_assign=None, on_revoke=None) -> None:
        self.calls.append("subscribe")
        self.topics = topics

    def poll(self, _timeout: float):
        if self.messages:
            return self.messages.pop(0)
        self.stop()
        return None

    def store_offsets(self, message) -> None:
        self.calls.append("store")

    def commit(self, message, asynchronous: bool) -> None:
        self.calls.append("commit")

    def seek(self, partition) -> None:
        self.calls.append("seek")

    def close(self) -> None:
        self.calls.append("close")

    def assign(self, partitions) -> None:
        self.calls.append("assign")


class SuccessfulProcessor:
    def __init__(self) -> None:
        self.calls = 0

    def process(self, source):
        self.calls += 1
        return ProcessingResult(ProcessingOutcome.VALID, "event-id")


class FailingProcessor:
    def process(self, source):
        raise ConnectionError("database unavailable")


def config(attempts: int = 2) -> IngestionConfig:
    return IngestionConfig(
        bootstrap_servers="broker:9092",
        database_url="postgresql://example",
        consumer_group="group",
        client_id="consumer",
        max_processing_attempts=attempts,
        retry_base_seconds=0.01,
        delivery_timeout_seconds=1,
    )


def test_successful_record_is_stored_then_committed(monkeypatch) -> None:
    message = FakeMessage()
    FakeKafkaConsumer.queued_messages = [message]
    monkeypatch.setattr("netpulse_ingestion.consumer.Consumer", FakeKafkaConsumer)
    processor = SuccessfulProcessor()
    registry = CollectorRegistry()
    consumer = IngestionConsumer(config(), processor, IngestionMetrics(registry))
    fake = FakeKafkaConsumer.latest
    fake.stop = lambda: setattr(consumer, "_running", False)
    monkeypatch.setattr("netpulse_ingestion.consumer.time.time", lambda: 1_750_000_000.0)

    consumer.run()

    assert processor.calls == 1
    assert fake.calls == ["subscribe", "store", "commit", "close"]
    output = generate_latest(registry).decode()
    assert 'netpulse_ingestion_records_total{outcome="valid"} 1.0' in output
    assert "netpulse_ingestion_processing_duration_seconds_count 1.0" in output
    assert "netpulse_ingestion_last_success_timestamp_seconds 1.75e+09" in output


def test_repeated_processing_failure_seeks_and_stops_without_commit(monkeypatch) -> None:
    message = FakeMessage()
    FakeKafkaConsumer.queued_messages = [message, message]
    monkeypatch.setattr("netpulse_ingestion.consumer.Consumer", FakeKafkaConsumer)
    monkeypatch.setattr("netpulse_ingestion.consumer.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("netpulse_ingestion.consumer.random.uniform", lambda _a, _b: 0)
    registry = CollectorRegistry()
    consumer = IngestionConsumer(config(attempts=2), FailingProcessor(), IngestionMetrics(registry))
    fake = FakeKafkaConsumer.latest

    with pytest.raises(RuntimeError, match="stopping without committing"):
        consumer.run()

    assert "seek" in fake.calls
    assert "commit" not in fake.calls
    assert fake.calls[-1] == "close"
    output = generate_latest(registry).decode()
    assert 'netpulse_ingestion_records_total{outcome="failed"} 2.0' in output
    assert "netpulse_ingestion_retries_total 1.0" in output


def test_source_conversion_handles_missing_key() -> None:
    message = FakeMessage(value=b'{"value":1}')
    message.key = lambda: None

    source = IngestionConsumer._to_source(message)

    assert source.key is None
    assert source.value == b'{"value":1}'
