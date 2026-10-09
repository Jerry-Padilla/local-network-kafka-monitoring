from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from netpulse_analytics.orchestration.models import DateRange
from netpulse_analytics.orchestration.repository import PostgresOrchestrationRepository


class FakeCursor:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class FakeConnection:
    def __init__(self, rows: dict[str, tuple[Any, ...] | None]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, object]] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> FakeCursor:
        normalized = " ".join(statement.split())
        self.statements.append((normalized, parameters))
        for token, row in self.rows.items():
            if token in normalized:
                return FakeCursor(row)
        return FakeCursor(None)


def _repository(
    monkeypatch: pytest.MonkeyPatch,
    rows: dict[str, tuple[Any, ...] | None],
) -> tuple[PostgresOrchestrationRepository, FakeConnection]:
    connection = FakeConnection(rows)
    monkeypatch.setattr(
        "netpulse_analytics.orchestration.repository.psycopg.connect",
        lambda *_args, **_kwargs: connection,
    )
    return PostgresOrchestrationRepository("postgresql://example"), connection


def test_source_snapshot_uses_half_open_utc_bounds_and_read_only_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest = datetime(2026, 10, 8, 23, 59, tzinfo=UTC)
    repository, connection = _repository(
        monkeypatch,
        {"AS observation_count": (10, 10, 2, 0, latest, latest, 4.0)},
    )
    selected = DateRange(date(2026, 10, 8), date(2026, 10, 8))

    snapshot = repository.load_source_snapshot(selected)

    assert snapshot.observation_count == 10
    assert snapshot.maximum_ingestion_delay_seconds == 4.0
    assert connection.statements[0][0] == (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    )
    assert connection.statements[-1][1] == {
        "window_start": selected.start,
        "window_end": selected.end,
    }


def test_reconciliation_result_reports_daily_and_incident_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _ = _repository(
        monkeypatch,
        {
            "AS daily_source_rows": (3, 3, 1),
            "AS source_incidents": (2, 2, 1),
        },
    )

    result = repository.reconcile(DateRange(date(2026, 10, 8), date(2026, 10, 8)))

    assert not result.valid
    with pytest.raises(RuntimeError, match="2 reconciliation mismatches"):
        result.require_valid()


def test_reporting_validation_rejects_bad_view_rows_or_wrong_job_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _ = _repository(
        monkeypatch,
        {"AS reporting_rows": (4, 1, 2), "AS run_matches": (False,)},
    )

    result = repository.validate_reporting(
        DateRange(date(2026, 10, 8), date(2026, 10, 8)),
        analytics_run_id=17,
    )

    assert not result.valid
    with pytest.raises(RuntimeError, match="reporting validation failed"):
        result.require_valid()


def test_database_check_propagates_transient_driver_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_connect(*_args: object, **_kwargs: object) -> None:
        raise OSError("database unavailable")

    monkeypatch.setattr(
        "netpulse_analytics.orchestration.repository.psycopg.connect",
        fail_connect,
    )

    with pytest.raises(OSError, match="database unavailable"):
        PostgresOrchestrationRepository("postgresql://example").check_database()
