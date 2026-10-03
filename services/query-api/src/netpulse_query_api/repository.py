"""Bounded, read-only PostgreSQL access for daily reliability pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from psycopg import Error
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from netpulse_query_api.models import CursorKey, DailyReliabilityFilters, DailyReliabilityRow

_FILTER_SQL = {
    "from_date": "date_utc >= %s",
    "through_date": "date_utc <= %s",
    "agent_id": "agent_id = %s",
    "endpoint_id": "endpoint_id = %s",
    "source_kind": "source_kind = %s",
    "probe_type": "probe_type = %s",
}
_CURSOR_SQL = (
    "(date_utc < %s OR (date_utc = %s AND "
    "(agent_id, endpoint_id, source_kind, probe_type) > (%s, %s, %s, %s)))"
)
_PROJECTION = (
    "date_utc, agent_id, endpoint_id, source_kind, probe_type, "
    "total_count, success_count, failure_count, success_rate_pct, "
    "latency_count, latency_sum_ms, mean_latency_ms, "
    "packet_loss_count, packet_loss_sum_pct, mean_packet_loss_pct"
)
_ORDER_BY = "date_utc DESC, agent_id ASC, endpoint_id ASC, source_kind ASC, probe_type ASC"


@dataclass(frozen=True, slots=True)
class ReliabilityPage:
    rows: tuple[DailyReliabilityRow, ...]
    has_more: bool


class ReliabilityRepository(Protocol):
    async def health(self) -> bool: ...

    async def list_daily(
        self, filters: DailyReliabilityFilters, cursor: CursorKey | None, limit: int
    ) -> ReliabilityPage: ...


class PostgresReliabilityRepository:
    def __init__(self, pool: AsyncConnectionPool, *, statement_timeout_ms: int = 3000) -> None:
        if type(statement_timeout_ms) is not int or not 1 <= statement_timeout_ms < 2**31:
            raise ValueError("statement timeout must be a positive 32-bit integer")
        self._pool = pool
        self._statement_timeout_ms = statement_timeout_ms

    async def health(self) -> bool:
        try:
            async with self._pool.connection() as connection, connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
            return True
        except Error:
            return False

    async def list_daily(
        self, filters: DailyReliabilityFilters, cursor: CursorKey | None, limit: int
    ) -> ReliabilityPage:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer between 1 and 200")

        where: list[str] = []
        params: list[object] = []
        for field, predicate in _FILTER_SQL.items():
            value = getattr(filters, field)
            if value is not None:
                where.append(predicate)
                params.append(value.value if field == "source_kind" else value)
        if cursor is not None:
            where.append(_CURSOR_SQL)
            params.extend(
                (
                    cursor.date_utc,
                    cursor.date_utc,
                    cursor.agent_id,
                    cursor.endpoint_id,
                    cursor.source_kind.value,
                    cursor.probe_type,
                )
            )

        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        query = (
            f"SELECT {_PROJECTION} FROM v_daily_probe_reliability{where_sql} "
            f"ORDER BY {_ORDER_BY} LIMIT %s"
        )
        params.append(limit + 1)

        async with (
            self._pool.connection() as connection,
            connection.transaction(),
            connection.cursor(row_factory=dict_row) as db_cursor,
        ):
            await db_cursor.execute("SET TRANSACTION READ ONLY")
            await db_cursor.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(self._statement_timeout_ms),),
            )
            await db_cursor.execute(query, tuple(params))
            records = await db_cursor.fetchall()

        rows = tuple(DailyReliabilityRow.model_validate(record) for record in records[:limit])
        return ReliabilityPage(rows=rows, has_more=len(records) > limit)
