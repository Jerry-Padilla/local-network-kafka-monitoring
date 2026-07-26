from __future__ import annotations

from datetime import UTC, datetime

from netpulse_contracts.models import SpeedTest
from netpulse_contracts.validation import validate_event
from netpulse_ingestion.processor_types import SourceRecord
from netpulse_ingestion.repository import PostgresEventRepository
from netpulse_simulator.scenarios import ScenarioGenerator


class FakeResult:
    def fetchone(self):
        return (1,)


class FakeConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def transaction(self):
        return self

    def execute(self, sql: str, params=None) -> FakeResult:
        self.executions.append((" ".join(sql.split()), params))
        return FakeResult()


class FakePool:
    latest = None

    def __init__(self, **kwargs) -> None:
        self.connection_instance = FakeConnection()
        self.opened = False
        self.closed = False
        type(self).latest = self

    def open(self, wait: bool) -> None:
        self.opened = wait

    def close(self) -> None:
        self.closed = True

    def connection(self) -> FakeConnection:
        return self.connection_instance


def source(offset: int = 1) -> SourceRecord:
    return SourceRecord(
        topic="network.measurements.raw.v1",
        partition=0,
        offset=offset,
        key="network-agent-wifi-01",
        value=b"{}",
    )


def test_repository_persists_every_phase1_typed_event(monkeypatch) -> None:
    monkeypatch.setattr("netpulse_ingestion.repository.ConnectionPool", FakePool)
    repository = PostgresEventRepository("postgresql://example")
    repository.open()
    generator = ScenarioGenerator(seed=9)
    records = generator.generate_round("healthy", datetime(2026, 7, 25, tzinfo=UTC))

    for offset, record in enumerate(records):
        repository.persist_event(validate_event(record.value), source(offset))

    speed_test = SpeedTest(
        event_id="c2128d60-f193-4421-8317-72b64e7038cd",
        event_type="network.speed_test",
        schema_version=1,
        agent_id="network-agent-wifi-01",
        agent_role="wifi_observer",
        event_time=datetime(2026, 7, 25, tzinfo=UTC),
        published_time=datetime(2026, 7, 25, tzinfo=UTC),
        sequence_number=100,
        correlation_id=None,
        source_version="0.1.0",
        provider="simulated",
        success=True,
        download_mbps=50,
        upload_mbps=10,
        latency_ms=20,
        duration_ms=1000,
        bytes_transferred=1000,
    )
    repository.persist_event(speed_test, source(100))
    repository.close()

    pool = FakePool.latest
    statements = [sql for sql, _params in pool.connection_instance.executions]
    assert any("INSERT INTO network_measurements" in sql for sql in statements)
    assert any("INSERT INTO service_checks" in sql for sql in statements)
    assert any("INSERT INTO agent_heartbeats" in sql for sql in statements)
    assert any("INSERT INTO speed_tests" in sql for sql in statements)
    assert pool.opened is True
    assert pool.closed is True


def test_failure_evidence_marking_and_healthcheck(monkeypatch) -> None:
    monkeypatch.setattr("netpulse_ingestion.repository.ConnectionPool", FakePool)
    repository = PostgresEventRepository("postgresql://example")

    repository.record_failure(
        source(),
        "EventValidationError",
        "bad event",
        [{"type": "missing"}],
    )
    repository.mark_dead_letter_published(source())

    assert repository.healthcheck() is True
    statements = [sql for sql, _params in FakePool.latest.connection_instance.executions]
    assert any("INSERT INTO processing_failures" in sql for sql in statements)
    assert any("UPDATE processing_failures" in sql for sql in statements)
