"""Live HTTP, database privilege, and query-plan acceptance for the query API."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.integration

API_URL = "http://query-api:8000"
ORDER_FIELDS = ("date_utc", "agent_id", "endpoint_id", "source_kind", "probe_type")


@dataclass(frozen=True, repr=False)
class SeededDaily:
    day: date
    agent_id: str
    endpoint_id: str
    probe_prefix: str


def _get(path: str, params: dict[str, str | int] | None = None) -> tuple[int, dict[str, object]]:
    url = f"{API_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        try:
            return error.code, json.load(error)
        except Exception:
            pass
    except Exception:
        pass
    pytest.fail("query API request failed", pytrace=False)


def _connect_safely(url: str) -> psycopg.Connection[tuple[object, ...]]:
    try:
        return psycopg.connect(url)
    except Exception:
        pass
    pytest.fail("database connection failed", pytrace=False)


def _check(condition: bool, message: str) -> None:
    if not condition:
        pytest.fail(message, pytrace=False)


@pytest.fixture
def seeded_daily() -> Iterator[SeededDaily]:
    if os.getenv("NETPULSE_INTEGRATION") != "1":
        pytest.skip("set NETPULSE_INTEGRATION=1")
    admin_url = os.environ["NETPULSE_ADMIN_DATABASE_URL"]
    suffix = uuid4().hex[:12]
    probe_prefix = f"api-acceptance-{suffix}-"
    day = date(2090, 1, 1) + timedelta(days=int(suffix[:6], 16) % 3000)
    seed_failed = False
    try:
        with _connect_safely(admin_url) as connection:
            agent = connection.execute(
                "SELECT agent_id, agent_role, display_name FROM agents ORDER BY agent_id LIMIT 1"
            ).fetchone()
            endpoint = connection.execute(
                "SELECT endpoint_id, endpoint_type, display_name "
                "FROM endpoints ORDER BY endpoint_id LIMIT 1"
            ).fetchone()
            _check(agent is not None and endpoint is not None, "fixture dimensions unavailable")
            connection.execute(
                "INSERT INTO dim_agent (agent_id, agent_role, display_name) "
                "VALUES (%s, %s, %s) ON CONFLICT (agent_id) DO NOTHING",
                agent,
            )
            connection.execute(
                "INSERT INTO dim_endpoint (endpoint_id, endpoint_type, display_name) "
                "VALUES (%s, %s, %s) ON CONFLICT (endpoint_id) DO NOTHING",
                endpoint,
            )
            connection.execute(
                "INSERT INTO dim_date (date_utc) VALUES (%s) ON CONFLICT DO NOTHING", (day,)
            )
            for index in range(3):
                probe = f"{probe_prefix}{index}"
                connection.execute(
                    "INSERT INTO dim_probe (source_kind, probe_type) "
                    "VALUES ('network_measurement', %s) ON CONFLICT DO NOTHING",
                    (probe,),
                )
                connection.execute(
                    """INSERT INTO fact_reliability_daily
                   (date_utc, agent_id, endpoint_id, source_kind, probe_type,
                    total_count, success_count, failure_count, latency_sum_ms,
                    latency_count, packet_loss_sum_pct, packet_loss_count)
                   VALUES (%s, %s, %s, 'network_measurement', %s,
                           2, 1, 1, %s, %s, NULL, 0)""",
                    (day, agent[0], endpoint[0], probe, 12.5 if index else None, int(index > 0)),
                )
    except psycopg.Error:
        seed_failed = True
    if seed_failed:
        pytest.fail("query API fixture seed failed", pytrace=False)
    try:
        yield SeededDaily(day, str(agent[0]), str(endpoint[0]), probe_prefix)
    finally:
        cleanup_failed = False
        try:
            with _connect_safely(admin_url) as connection:
                connection.execute(
                    "DELETE FROM fact_reliability_daily WHERE date_utc = %s AND probe_type LIKE %s",
                    (day, f"{probe_prefix}%"),
                )
                connection.execute(
                    "DELETE FROM dim_probe WHERE probe_type LIKE %s", (f"{probe_prefix}%",)
                )
                connection.execute(
                    "DELETE FROM dim_date WHERE date_utc = %s "
                    "AND NOT EXISTS (SELECT 1 FROM fact_reliability_daily WHERE date_utc = %s)",
                    (day, day),
                )
        except psycopg.Error:
            cleanup_failed = True
        if cleanup_failed:
            pytest.fail("query API fixture cleanup failed", pytrace=False)


def test_live_http_filters_types_and_cursor(seeded_daily: SeededDaily) -> None:
    day = seeded_daily.day
    agent_id = seeded_daily.agent_id
    endpoint_id = seeded_daily.endpoint_id
    prefix = seeded_daily.probe_prefix
    health_status, health = _get("/healthz")
    _check(health_status == 200 and health == {"status": "ok"}, "query API health failed")

    filters: dict[str, str | int] = {
        "from_date": day.isoformat(),
        "through_date": day.isoformat(),
        "agent_id": agent_id,
        "endpoint_id": endpoint_id,
        "source_kind": "network_measurement",
        "limit": 2,
    }
    status, first = _get("/v1/reliability/daily", filters)
    _check(status == 200, "first page status was not 200")
    _check(first["limit"] == 2, "first page limit was wrong")
    first_items = first["items"]
    _check(isinstance(first_items, list), "first page items were not a list")
    _check(len(first_items) == 2, "first page item count was wrong")
    cursor = first["next_cursor"]
    _check(isinstance(cursor, str) and bool(cursor), "first page cursor was invalid")

    status, second = _get("/v1/reliability/daily", {**filters, "cursor": cursor})
    _check(status == 200 and second["next_cursor"] is None, "second page was invalid")
    second_items = second["items"]
    _check(isinstance(second_items, list) and len(second_items) == 1, "second page count was wrong")
    items = first_items + second_items
    _check(all(isinstance(item, dict) for item in items), "page item shape was invalid")
    keys = [tuple(item[field] for field in ORDER_FIELDS) for item in items]
    _check(len(set(keys)) == 3, "pages repeated or omitted an ordering key")
    _check(
        [item["probe_type"] for item in items] == [f"{prefix}{i}" for i in range(3)],
        "page ordering was wrong",
    )
    for item in items:
        _check(item["date_utc"] == day.isoformat(), "date filter was not honored")
        _check(
            item["agent_id"] == agent_id and item["endpoint_id"] == endpoint_id,
            "agent or endpoint filter was not honored",
        )
        _check(item["source_kind"] == "network_measurement", "source filter was not honored")
        for field in ("total_count", "success_count", "failure_count", "latency_count"):
            _check(type(item[field]) is int, "count field was not a JSON integer")
        for field in (
            "success_rate_pct",
            "latency_sum_ms",
            "mean_latency_ms",
            "packet_loss_sum_pct",
            "mean_packet_loss_pct",
        ):
            _check(
                item[field] is None or type(item[field]) in (int, float),
                "measure field was neither a JSON number nor null",
            )
    _check(items[0]["mean_latency_ms"] is None, "null mean latency was incorrect")
    _check(items[1]["mean_latency_ms"] == 12.5, "numeric mean latency was incorrect")

    status, filtered = _get("/v1/reliability/daily", {**filters, "probe_type": f"{prefix}1"})
    _check(status == 200 and len(filtered["items"]) == 1, "probe filter was not honored")
    mismatch_status, _ = _get(
        "/v1/reliability/daily", {**filters, "probe_type": f"{prefix}1", "cursor": cursor}
    )
    _check(mismatch_status == 422, "mismatched cursor was not rejected")


def _denied_statements() -> tuple[str, ...]:
    return (
        "SELECT * FROM network_measurements",
        "INSERT INTO network_measurements DEFAULT VALUES",
        "UPDATE network_measurements SET success = FALSE WHERE FALSE",
        "DELETE FROM network_measurements WHERE FALSE",
    )


def test_dedicated_login_cannot_read_or_mutate_operational_rows() -> None:
    if os.getenv("NETPULSE_INTEGRATION") != "1":
        pytest.skip("set NETPULSE_INTEGRATION=1")
    reader_url = os.environ["NETPULSE_QUERY_API_DATABASE_URL"]
    with _connect_safely(reader_url) as connection:
        connection.execute("SELECT COUNT(*) FROM v_daily_probe_reliability")
        for view in (
            "v_incident_summary",
            "v_sre_agent_status",
            "v_sre_pipeline_status",
            "v_grafana_live_measurements",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(view)))
            connection.rollback()
        for statement in _denied_statements():
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)
            connection.rollback()


def test_update_probe_does_not_need_select_privilege() -> None:
    if os.getenv("NETPULSE_INTEGRATION") != "1":
        pytest.skip("set NETPULSE_INTEGRATION=1")
    role = sql.Identifier(f"query_api_update_probe_{uuid4().hex}")
    with _connect_safely(os.environ["NETPULSE_ADMIN_DATABASE_URL"]) as connection:
        connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(role))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        connection.execute(
            sql.SQL("GRANT UPDATE (success) ON network_measurements TO {}").format(role)
        )
        connection.execute(sql.SQL("SET LOCAL ROLE {}").format(role))
        connection.execute(_denied_statements()[2])
        connection.rollback()


def _plan_nodes(node: dict[str, object]) -> Iterator[dict[str, object]]:
    yield node
    for child in node.get("Plans", []):
        yield from _plan_nodes(child)


def _uses_api_index_without_sort(plan: dict[str, object]) -> bool:
    nodes = list(_plan_nodes(plan))
    return any(
        node.get("Index Name") == "idx_fact_reliability_daily_api_order" for node in nodes
    ) and all(node.get("Node Type") not in {"Sort", "Incremental Sort"} for node in nodes)


def test_plan_gate_rejects_incremental_sort() -> None:
    plan = {
        "Node Type": "Limit",
        "Plans": [
            {
                "Node Type": "Incremental Sort",
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Index Name": "idx_fact_reliability_daily_api_order",
                    }
                ],
            }
        ],
    }
    assert not _uses_api_index_without_sort(plan)


def test_daily_order_query_uses_api_index_without_sort(
    seeded_daily: SeededDaily,
) -> None:
    day = seeded_daily.day
    admin_url = os.environ["NETPULSE_ADMIN_DATABASE_URL"]
    with _connect_safely(admin_url) as connection:
        connection.execute("SET enable_seqscan = off")
        for where, params in (("", ()), ("WHERE date_utc >= %s AND date_utc <= %s", (day, day))):
            plan = connection.execute(
                "EXPLAIN (FORMAT JSON) SELECT date_utc, agent_id, endpoint_id, "
                "source_kind, probe_type, total_count, success_count, failure_count, "
                "success_rate_pct, latency_count, latency_sum_ms, mean_latency_ms, "
                "packet_loss_count, packet_loss_sum_pct, mean_packet_loss_pct "
                f"FROM v_daily_probe_reliability {where} "
                "ORDER BY date_utc DESC, agent_id ASC, endpoint_id ASC, "
                "source_kind ASC, probe_type ASC LIMIT 3",
                params,
            ).fetchone()
            assert plan is not None
            assert _uses_api_index_without_sort(plan[0][0]["Plan"])
