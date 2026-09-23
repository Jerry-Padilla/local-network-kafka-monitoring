from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from netpulse_analytics.cli import DateSelection
from netpulse_analytics.repository import PostgresAnalyticsRepository
from psycopg import sql

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.getenv("NETPULSE_INTEGRATION") == "1"


def _insert_raw(
    connection: psycopg.Connection[tuple[object, ...]],
    event_id: UUID,
    agent_id: str,
    event_time: datetime,
    offset: int,
    event_type: str,
) -> None:
    connection.execute(
        """
        INSERT INTO raw_events (
            event_id, event_type, schema_version, agent_id, agent_role,
            event_time, published_time, sequence_number, source_version,
            source_topic, source_partition, source_offset, payload, quality_status
        ) VALUES (%s, %s, 1, %s, 'wired_reference', %s, %s, %s,
                  'analytics-test', 'analytics.test', 0, %s, '{}'::jsonb, 'valid')
        """,
        (event_id, event_type, agent_id, event_time, event_time, offset, offset),
    )


@pytest.fixture
def analytics_fixture() -> Iterator[tuple[str, str, str, str]]:
    if not _integration_enabled():
        pytest.skip("set NETPULSE_INTEGRATION=1")
    database_url = os.environ["NETPULSE_DATABASE_URL"]
    suffix = uuid4().hex[:12]
    agent_id = f"analytics-agent-{suffix}"
    second_agent_id = f"analytics-agent-2-{suffix}"
    endpoint_id = f"analytics-endpoint-{suffix}"
    endpoint_ids = [endpoint_id, *(f"analytics-endpoint-{index}-{suffix}" for index in (2, 3))]
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO agents (agent_id, agent_role, display_name)
               VALUES (%s, %s, %s), (%s, %s, %s)""",
            (
                agent_id,
                "wired_reference",
                "Analytics fixture",
                second_agent_id,
                "wifi_observer",
                "Analytics fixture two",
            ),
        )
        for current_endpoint in endpoint_ids:
            connection.execute(
                """INSERT INTO endpoints
                   (endpoint_id, endpoint_type, display_name, fabricated_sample)
                   VALUES (%s, 'external_ip', %s, TRUE)""",
                (current_endpoint, current_endpoint),
            )
    try:
        yield database_url, agent_id, second_agent_id, endpoint_id
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM network_incidents WHERE affected_agents ?| %s",
                ([agent_id, second_agent_id],),
            )
            connection.execute(
                "DELETE FROM raw_events WHERE agent_id IN (%s, %s)",
                (agent_id, second_agent_id),
            )
        PostgresAnalyticsRepository(database_url).run(
            DateSelection(date(2033, 3, 8), date(2033, 3, 10), False)
        )
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM dim_endpoint WHERE endpoint_id LIKE %s",
                (f"%-{endpoint_id.split('-')[-1]}",),
            )
            connection.execute(
                "DELETE FROM dim_agent WHERE agent_id IN (%s, %s)",
                (agent_id, second_agent_id),
            )
            connection.execute(
                "DELETE FROM endpoints WHERE endpoint_id LIKE %s",
                (f"%-{endpoint_id.split('-')[-1]}",),
            )
            connection.execute(
                "DELETE FROM agents WHERE agent_id IN (%s, %s)",
                (agent_id, second_agent_id),
            )


def _insert_measurement(
    database_url: str,
    agent_id: str,
    endpoint_id: str,
    event_time: datetime,
    offset: int,
    event_id: UUID | None = None,
) -> UUID:
    resolved_event_id = event_id or uuid4()
    with psycopg.connect(database_url) as connection:
        _insert_raw(
            connection,
            resolved_event_id,
            agent_id,
            event_time,
            offset,
            "network.measurement",
        )
        connection.execute(
            """INSERT INTO network_measurements
               (event_id, agent_id, target_id, event_time, measurement_type,
                success, latency_ms, packet_loss_pct)
               VALUES (%s, %s, %s, %s, 'external_ping', TRUE, 10.0, 0.0)
               ON CONFLICT (event_id) DO NOTHING""",
            (resolved_event_id, agent_id, endpoint_id, event_time),
        )
    return resolved_event_id


@pytest.mark.skipif(not _integration_enabled(), reason="set NETPULSE_INTEGRATION=1")
def test_daily_refresh_is_replay_safe_event_time_based_and_clears_stale_dates(
    analytics_fixture: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    database_url, agent_id, _, endpoint_id = analytics_fixture
    first_id = _insert_measurement(
        database_url,
        agent_id,
        endpoint_id,
        datetime(2033, 3, 8, 23, 59, 59, tzinfo=UTC),
        810001,
    )
    _insert_measurement(
        database_url,
        agent_id,
        endpoint_id,
        datetime(2033, 3, 9, 0, 0, tzinfo=UTC),
        810002,
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO network_measurements
               SELECT * FROM network_measurements WHERE event_id = %s
               ON CONFLICT (event_id) DO NOTHING""",
            (first_id,),
        )
        service_id = uuid4()
        _insert_raw(
            connection,
            service_id,
            agent_id,
            datetime(2033, 3, 9, 1, tzinfo=UTC),
            810003,
            "service.check",
        )
        connection.execute(
            """INSERT INTO service_checks
               (event_id, agent_id, endpoint_id, event_time, check_type, success,
                total_duration_ms, timeout)
               VALUES (%s, %s, %s, %s, 'http', FALSE, NULL, FALSE)""",
            (service_id, agent_id, endpoint_id, datetime(2033, 3, 9, 1, tzinfo=UTC)),
        )

    repository = PostgresAnalyticsRepository(database_url)
    repository.run(DateSelection(date(2033, 3, 8), date(2033, 3, 9), False))
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """SELECT date_utc, SUM(total_count)
               FROM fact_reliability_daily WHERE agent_id = %s
               GROUP BY date_utc ORDER BY date_utc""",
            (agent_id,),
        ).fetchall()
        nullable_latency = connection.execute(
            """SELECT latency_count, latency_sum_ms, mean_latency_ms
               FROM v_daily_probe_reliability
               WHERE agent_id = %s AND source_kind = 'service_check'""",
            (agent_id,),
        ).fetchone()
        distinct_source_events = connection.execute(
            """SELECT COUNT(*) FROM (
                   SELECT event_id FROM network_measurements WHERE agent_id = %s
                   UNION ALL
                   SELECT event_id FROM service_checks WHERE agent_id = %s
               ) typed_events""",
            (agent_id, agent_id),
        ).fetchone()
    assert rows == [(date(2033, 3, 8), 1), (date(2033, 3, 9), 2)]
    assert sum(row[1] for row in rows) == distinct_source_events[0]
    assert nullable_latency == (0, None, None)

    late_id = _insert_measurement(
        database_url,
        agent_id,
        endpoint_id,
        datetime(2033, 3, 8, 12, tzinfo=UTC),
        810004,
    )
    with psycopg.connect(database_url) as connection:
        before = connection.execute(
            """SELECT total_count FROM fact_reliability_daily
               WHERE agent_id = %s AND date_utc = '2033-03-08'""",
            (agent_id,),
        ).fetchone()
    assert before == (1,)
    repository.run(DateSelection(date(2033, 3, 8), date(2033, 3, 8), False))
    with psycopg.connect(database_url) as connection:
        after = connection.execute(
            """SELECT total_count FROM fact_reliability_daily
               WHERE agent_id = %s AND date_utc = '2033-03-08'""",
            (agent_id,),
        ).fetchone()
        untouched = connection.execute(
            """SELECT SUM(total_count) FROM fact_reliability_daily
               WHERE agent_id = %s AND date_utc = '2033-03-09'""",
            (agent_id,),
        ).fetchone()
        connection.execute("DELETE FROM raw_events WHERE event_id IN (%s, %s)", (first_id, late_id))
    assert after == (2,)
    assert untouched == (2,)

    repository.run(DateSelection(date(2033, 3, 8), date(2033, 3, 8), False))
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """SELECT COUNT(*) FROM fact_reliability_daily
               WHERE agent_id = %s AND date_utc = '2033-03-08'""",
            (agent_id,),
        ).fetchone() == (0,)
        connection.execute("DELETE FROM raw_events WHERE agent_id = %s", (agent_id,))
    repository.run(DateSelection(None, None, True))
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fact_reliability_daily WHERE agent_id = %s",
            (agent_id,),
        ).fetchone() == (0,)


@pytest.mark.skipif(not _integration_enabled(), reason="set NETPULSE_INTEGRATION=1")
def test_incident_snapshot_cardinality_revision_and_transactional_rollback(
    analytics_fixture: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, agent_id, second_agent_id, endpoint_id = analytics_fixture
    suffix = endpoint_id.split("-")[-1]
    endpoint_ids = [endpoint_id, f"analytics-endpoint-2-{suffix}", f"analytics-endpoint-3-{suffix}"]
    incident_id = uuid4()
    event_id = _insert_measurement(
        database_url,
        agent_id,
        endpoint_id,
        datetime(2033, 3, 10, 1, tzinfo=UTC),
        820001,
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO network_incidents (
                incident_id, incident_key, incident_type, start_time, status, severity,
                confidence_score, affected_agents, affected_endpoints, evidence,
                rule_version, duration_ms, summary, recommended_action, state_revision,
                positive_observations, recovery_observations, last_observed_at
            ) VALUES (
                %s, %s, 'isp_outage', %s, 'open', 'critical', 0.9,
                %s::jsonb, %s::jsonb, '[]'::jsonb, 'analytics-test-v1', 1000,
                'Fixture incident', 'Inspect fixture', 1, 2, 0, %s
            )""",
            (
                incident_id,
                f"analytics-{incident_id}",
                datetime(2033, 3, 10, 1, tzinfo=UTC),
                psycopg.types.json.Jsonb([agent_id, second_agent_id]),
                psycopg.types.json.Jsonb(endpoint_ids),
                datetime(2033, 3, 10, 1, tzinfo=UTC),
            ),
        )
    repository = PostgresAnalyticsRepository(database_url)
    selection = DateSelection(date(2033, 3, 10), date(2033, 3, 10), False)
    repository.run(selection)
    with psycopg.connect(database_url) as connection:
        summary = connection.execute(
            """SELECT affected_agent_count, affected_endpoint_count
               FROM v_incident_summary WHERE incident_id = %s""",
            (incident_id,),
        ).fetchone()
        connection.execute(
            """UPDATE network_incidents SET status = 'resolved', end_time = %s,
               state_revision = 2, duration_ms = 2000, affected_endpoints = %s::jsonb
               WHERE incident_id = %s""",
            (
                datetime(2033, 3, 10, 1, 0, 2, tzinfo=UTC),
                psycopg.types.json.Jsonb(endpoint_ids[:2]),
                incident_id,
            ),
        )
    assert summary == (2, 3)
    repository.run(selection)
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT status, state_revision, duration_ms FROM fact_incident WHERE incident_id = %s",
            (incident_id,),
        ).fetchone() == ("resolved", 2, 2000.0)
        assert connection.execute(
            "SELECT COUNT(*) FROM bridge_incident_endpoint WHERE incident_id = %s",
            (incident_id,),
        ).fetchone() == (2,)
        old_daily = connection.execute(
            """SELECT total_count FROM fact_reliability_daily
               WHERE agent_id = %s AND date_utc = '2033-03-10'""",
            (agent_id,),
        ).fetchone()
        old_runs = connection.execute("SELECT COUNT(*) FROM analytics_job_runs").fetchone()

    _insert_measurement(
        database_url,
        agent_id,
        endpoint_id,
        datetime(2033, 3, 10, 2, tzinfo=UTC),
        820002,
    )

    def fail_incidents(_connection: object) -> int:
        raise RuntimeError("injected incident failure")

    monkeypatch.setattr(repository, "_refresh_incidents", fail_incidents)
    with pytest.raises(RuntimeError, match="injected incident failure"):
        repository.run(selection)
    with psycopg.connect(database_url) as connection:
        assert (
            connection.execute(
                """SELECT total_count FROM fact_reliability_daily
               WHERE agent_id = %s AND date_utc = '2033-03-10'""",
                (agent_id,),
            ).fetchone()
            == old_daily
        )
        assert connection.execute(
            "SELECT status, state_revision FROM fact_incident WHERE incident_id = %s",
            (incident_id,),
        ).fetchone() == ("resolved", 2)
        assert connection.execute("SELECT COUNT(*) FROM analytics_job_runs").fetchone() == old_runs
        connection.execute("DELETE FROM raw_events WHERE event_id = %s", (event_id,))


@pytest.mark.skipif(not _integration_enabled(), reason="set NETPULSE_INTEGRATION=1")
def test_reporting_role_can_read_only_views() -> None:
    admin_database_url = os.environ["NETPULSE_ADMIN_DATABASE_URL"]
    role_name = f"netpulse_report_test_{uuid4().hex}"
    password = secrets.token_urlsafe(24)
    with psycopg.connect(admin_database_url, autocommit=True) as admin_connection:
        admin_connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role_name), sql.Literal(password)
            )
        )
        admin_connection.execute(
            sql.SQL("GRANT netpulse_report TO {}").format(sql.Identifier(role_name))
        )
    try:
        reader_url = psycopg.conninfo.make_conninfo(
            admin_database_url,
            user=role_name,
            password=password,
        )
        with psycopg.connect(reader_url) as reader_connection:
            reader_connection.execute("SELECT COUNT(*) FROM v_daily_probe_reliability")
            reader_connection.execute("SELECT COUNT(*) FROM v_incident_summary")
            denied_statements = (
                "INSERT INTO dim_date (date_utc) VALUES ('2031-01-01')",
                "UPDATE agents SET display_name = display_name",
                "SELECT * FROM network_measurements",
            )
            for statement in denied_statements:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    reader_connection.execute(statement)
                reader_connection.rollback()
    finally:
        with psycopg.connect(admin_database_url, autocommit=True) as admin_connection:
            admin_connection.execute(
                sql.SQL("REVOKE netpulse_report FROM {}").format(sql.Identifier(role_name))
            )
            admin_connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))
