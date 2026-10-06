"""Database boundary contract for the daily reliability reader."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest
from netpulse_query_api.models import CursorKey, DailyReliabilityFilters, SourceKind
from netpulse_query_api.repository import PostgresReliabilityRepository
from psycopg import OperationalError
from psycopg.rows import dict_row


class FakeCursor:
    def __init__(self, pool: FakePool) -> None:
        self.pool = pool

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        assert self.pool.in_transaction or query == "SELECT 1"
        if self.pool.error is not None:
            raise self.pool.error
        self.pool.statements.append((query, params))

    async def fetchall(self) -> list[dict[str, Any]]:
        if self.pool.row_batches:
            return self.pool.row_batches.pop(0)
        return self.pool.rows


class FakeTransaction:
    def __init__(self, pool: FakePool) -> None:
        self.pool = pool

    async def __aenter__(self) -> FakeTransaction:
        self.pool.in_transaction = True
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.pool.in_transaction = False


class FakeConnection:
    def __init__(self, pool: FakePool) -> None:
        self.pool = pool

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self.pool)

    def cursor(self, *, row_factory: object | None = None) -> FakeCursor:
        self.pool.row_factories.append(row_factory)
        return FakeCursor(self.pool)


class FakePool:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        row_batches: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        self.rows = rows or []
        self.row_batches = row_batches or []
        self.statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.row_factories: list[object | None] = []
        self.in_transaction = False
        self.error: Exception | None = None

    async def __aenter__(self) -> FakeConnection:
        return FakeConnection(self)

    async def __aexit__(self, *_args: object) -> None:
        return None

    def connection(self) -> FakePool:
        return self


def _row(agent_id: str, endpoint_id: str, *, day: date = date(2026, 10, 1)) -> dict[str, Any]:
    return {
        "date_utc": day,
        "agent_id": agent_id,
        "endpoint_id": endpoint_id,
        "source_kind": "service_check",
        "probe_type": "http",
        "total_count": 2,
        "success_count": 1,
        "failure_count": 1,
        "success_rate_pct": 50.0,
        "latency_count": 0,
        "latency_sum_ms": None,
        "mean_latency_ms": None,
        "packet_loss_count": 0,
        "packet_loss_sum_pct": None,
        "mean_packet_loss_pct": None,
    }


def test_list_daily_uses_fixed_view_projection_and_bound_filters() -> None:
    injected_agent = "agent' OR TRUE --"
    pool = FakePool([_row("agent-a", "endpoint-a")])
    repository = PostgresReliabilityRepository(pool, statement_timeout_ms=2500)
    filters = DailyReliabilityFilters(
        from_date=date(2026, 9, 1),
        through_date=date(2026, 10, 1),
        agent_id=injected_agent,
        endpoint_id="endpoint-a",
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type="http",
    )
    page = asyncio.run(repository.list_daily(filters, None, 2))

    assert page.has_more is False
    assert len(page.rows) == 1
    assert page.rows[0].total_count == 2
    assert page.rows[0].source_kind is SourceKind.SERVICE_CHECK
    assert pool.in_transaction is False
    assert pool.row_factories == [dict_row]
    assert pool.statements[0] == ("SET TRANSACTION READ ONLY", None)
    assert pool.statements[1] == (
        "SELECT set_config('statement_timeout', %s, true)",
        ("2500",),
    )
    query, params = pool.statements[2]
    normalized = " ".join(query.split())
    assert normalized.startswith(
        "SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type, "
        "total_count, success_count, failure_count, success_rate_pct, "
        "latency_count, latency_sum_ms, mean_latency_ms, "
        "packet_loss_count, packet_loss_sum_pct, mean_packet_loss_pct "
        "FROM v_daily_probe_reliability WHERE "
    )
    assert "FROM fact_reliability_daily" not in query
    assert "SELECT *" not in query
    assert injected_agent not in query
    assert "date_utc >= %s" in normalized
    assert "date_utc <= %s" in normalized
    assert "agent_id = %s" in normalized
    assert "endpoint_id = %s" in normalized
    assert "source_kind = %s" in normalized
    assert "probe_type = %s" in normalized
    assert normalized.endswith(
        "ORDER BY date_utc DESC, agent_id ASC, endpoint_id ASC, "
        "source_kind ASC, probe_type ASC LIMIT %s"
    )
    assert params == (
        date(2026, 9, 1),
        date(2026, 10, 1),
        injected_agent,
        "endpoint-a",
        "service_check",
        "http",
        3,
    )


def test_cursor_page_uses_two_bounded_index_seek_queries_in_order() -> None:
    pool = FakePool(
        row_batches=[
            [_row(" agent-a ", " endpoint-b ")],
            [
                _row("agent-a", "endpoint-a", day=date(2026, 9, 30)),
                _row("agent-b", "endpoint-a", day=date(2026, 9, 30)),
            ],
        ]
    )
    repository = PostgresReliabilityRepository(pool)
    cursor = CursorKey(
        date_utc=date(2026, 10, 1),
        agent_id=" agent-a ",
        endpoint_id=" endpoint-a ",
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type=" http ",
    )

    page = asyncio.run(repository.list_daily(DailyReliabilityFilters(), cursor, 2))

    assert page.has_more is True
    assert [(row.date_utc, row.agent_id, row.endpoint_id) for row in page.rows] == [
        (date(2026, 10, 1), " agent-a ", " endpoint-b "),
        (date(2026, 9, 30), "agent-a", "endpoint-a"),
    ]
    same_date_query, same_date_params = pool.statements[2]
    older_date_query, older_date_params = pool.statements[3]
    same_date_sql = " ".join(same_date_query.split())
    older_date_sql = " ".join(older_date_query.split())
    assert " OR " not in same_date_sql
    assert "date_utc = %s" in same_date_sql
    assert "(agent_id, endpoint_id, source_kind, probe_type) > (%s, %s, %s, %s)" in same_date_sql
    assert same_date_params == (
        date(2026, 10, 1),
        " agent-a ",
        " endpoint-a ",
        "service_check",
        " http ",
        3,
    )
    assert " OR " not in older_date_sql
    assert "date_utc < %s" in older_date_sql
    assert "(agent_id, endpoint_id, source_kind, probe_type) >" not in older_date_sql
    assert older_date_params == (date(2026, 10, 1), 2)


def test_list_daily_truncates_lookahead_and_keeps_complete_same_date_key() -> None:
    pool = FakePool([_row("agent-a", "endpoint-a"), _row("agent-a", "endpoint-b")])
    repository = PostgresReliabilityRepository(pool)

    page = asyncio.run(repository.list_daily(DailyReliabilityFilters(), None, 1))

    assert page.has_more is True
    assert len(page.rows) == 1
    assert (
        page.rows[-1].date_utc,
        page.rows[-1].agent_id,
        page.rows[-1].endpoint_id,
        page.rows[-1].source_kind,
        page.rows[-1].probe_type,
    ) == (date(2026, 10, 1), "agent-a", "endpoint-a", SourceKind.SERVICE_CHECK, "http")
    query, params = pool.statements[-1]
    assert "LIMIT %s" in query
    assert params == (2,)


def test_health_runs_only_select_one_and_hides_connection_errors() -> None:
    pool = FakePool()
    repository = PostgresReliabilityRepository(pool)

    assert asyncio.run(repository.health()) is True
    assert pool.statements == [("SELECT 1", None)]

    pool.error = OperationalError("unavailable")
    assert asyncio.run(repository.health()) is False


def test_list_daily_propagates_dependency_errors() -> None:
    pool = FakePool()
    pool.error = OperationalError("unavailable")
    repository = PostgresReliabilityRepository(pool)

    with pytest.raises(OperationalError):
        asyncio.run(repository.list_daily(DailyReliabilityFilters(), None, 1))


def test_repository_rejects_unbounded_limits_and_statement_timeouts() -> None:
    pool = FakePool()
    for timeout in (0, -1, 2**31, True):
        with pytest.raises(ValueError):
            PostgresReliabilityRepository(pool, statement_timeout_ms=timeout)
    repository = PostgresReliabilityRepository(pool)
    for limit in (0, 201, True):
        with pytest.raises(ValueError):
            asyncio.run(repository.list_daily(DailyReliabilityFilters(), None, limit))
