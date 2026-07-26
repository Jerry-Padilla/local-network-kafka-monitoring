import json
from datetime import UTC, datetime

import pytest
from netpulse_contracts.topics import DEAD_LETTER_TOPIC, VALID_MEASUREMENTS_TOPIC
from netpulse_ingestion.processor import EventProcessor, ProcessingOutcome
from netpulse_ingestion.processor_types import SourceRecord
from netpulse_simulator.scenarios import ScenarioGenerator

FIXED_TIME = datetime(2026, 7, 25, 12, tzinfo=UTC)


class FakeRepository:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.events = []
        self.failures = []

    def persist_event(self, event, source) -> None:
        self.calls.append("persist")
        self.events.append((event, source))

    def record_failure(self, source, error_class, error_message, validation_errors) -> None:
        self.calls.append("record_failure")
        self.failures.append((source, error_class, error_message, validation_errors))

    def mark_dead_letter_published(self, source) -> None:
        self.calls.append("mark_dead_letter_published")


class FakePublisher:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.records = []

    def publish(self, topic: str, key: str | None, value: bytes) -> None:
        self.calls.append(f"publish:{topic}")
        self.records.append((topic, key, value))


def source(value: bytes, offset: int = 1) -> SourceRecord:
    return SourceRecord(
        topic="network.measurements.raw.v1",
        partition=0,
        offset=offset,
        key="network-agent-wifi-01",
        value=value,
    )


def test_valid_measurement_persists_before_valid_topic_publication() -> None:
    calls: list[str] = []
    repository = FakeRepository(calls)
    publisher = FakePublisher(calls)
    processor = EventProcessor(repository, publisher)
    record = ScenarioGenerator(seed=3).generate_round("high-latency", FIXED_TIME)[0]

    result = processor.process(source(record.value))

    assert result.outcome == ProcessingOutcome.VALID
    assert calls == ["persist", f"publish:{VALID_MEASUREMENTS_TOPIC}"]
    assert len(repository.events) == 1


def test_invalid_record_is_stored_before_dead_letter_and_marked_after_ack() -> None:
    calls: list[str] = []
    repository = FakeRepository(calls)
    publisher = FakePublisher(calls)
    processor = EventProcessor(repository, publisher)

    result = processor.process(source(b'{"broken":'))

    assert result.outcome == ProcessingOutcome.DEAD_LETTERED
    assert calls == [
        "record_failure",
        f"publish:{DEAD_LETTER_TOPIC}",
        "mark_dead_letter_published",
    ]
    dead_letter = json.loads(publisher.records[0][2])
    assert dead_letter["source_offset"] == 1
    assert dead_letter["original_payload"] == '{"broken":'


def test_unknown_agent_is_dead_lettered_not_retried_as_database_error() -> None:
    calls: list[str] = []
    repository = FakeRepository(calls)
    publisher = FakePublisher(calls)
    processor = EventProcessor(repository, publisher)
    record = ScenarioGenerator(seed=3).generate_round("healthy", FIXED_TIME)[0]
    payload = json.loads(record.value)
    payload["agent_id"] = "unknown-agent-01"

    result = processor.process(source(json.dumps(payload).encode()))

    assert result.outcome == ProcessingOutcome.DEAD_LETTERED
    assert repository.failures


def test_database_failure_prevents_output_publication() -> None:
    calls: list[str] = []
    repository = FakeRepository(calls)
    publisher = FakePublisher(calls)

    def fail(_event, _source) -> None:
        calls.append("persist_failed")
        raise ConnectionError("database unavailable")

    repository.persist_event = fail
    processor = EventProcessor(repository, publisher)
    record = ScenarioGenerator(seed=3).generate_round("healthy", FIXED_TIME)[0]

    with pytest.raises(ConnectionError, match="database unavailable"):
        processor.process(source(record.value))

    assert calls == ["persist_failed"]
