"""Reconcile current analytics facts with deduplicated operational tables."""

from __future__ import annotations

import os
from datetime import date

import psycopg

Grain = tuple[date, str, str, str, str]
Counts = tuple[int, int, int]


def _source_counts(connection: psycopg.Connection[tuple[object, ...]]) -> dict[Grain, Counts]:
    rows = connection.execute(
        """
        WITH observations AS (
            SELECT (event_time AT TIME ZONE 'UTC')::date AS date_utc,
                   agent_id, target_id AS endpoint_id,
                   'network_measurement'::text AS source_kind,
                   measurement_type AS probe_type, success
            FROM network_measurements
            UNION ALL
            SELECT (event_time AT TIME ZONE 'UTC')::date,
                   agent_id, endpoint_id, 'service_check'::text,
                   check_type, success
            FROM service_checks
        )
        SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type,
               COUNT(*), COUNT(*) FILTER (WHERE success),
               COUNT(*) FILTER (WHERE NOT success)
        FROM observations
        GROUP BY date_utc, agent_id, endpoint_id, source_kind, probe_type
        """
    ).fetchall()
    return {(row[0], row[1], row[2], row[3], row[4]): (row[5], row[6], row[7]) for row in rows}


def _fact_counts(connection: psycopg.Connection[tuple[object, ...]]) -> dict[Grain, Counts]:
    rows = connection.execute(
        """
        SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type,
               total_count, success_count, failure_count
        FROM fact_reliability_daily
        """
    ).fetchall()
    return {(row[0], row[1], row[2], row[3], row[4]): (row[5], row[6], row[7]) for row in rows}


def main() -> int:
    database_url = os.environ["NETPULSE_DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        source = _source_counts(connection)
        fact = _fact_counts(connection)
        source_incidents = connection.execute("SELECT COUNT(*) FROM network_incidents").fetchone()
        fact_incidents = connection.execute("SELECT COUNT(*) FROM fact_incident").fetchone()

    mismatches = [key for key in source.keys() | fact.keys() if source.get(key) != fact.get(key)]
    if mismatches:
        for key in sorted(mismatches)[:10]:
            print(
                f"FAILED: daily grain {key!r}: source={source.get(key)!r}, fact={fact.get(key)!r}"
            )
        print(f"FAILED: {len(mismatches)} daily grains do not reconcile")
        return 1
    if source_incidents != fact_incidents:
        print(f"FAILED: incident counts differ: source={source_incidents}, fact={fact_incidents}")
        return 1

    print(
        f"Phase 5A analytics invariants passed: {len(fact)} daily grains, "
        f"{fact_incidents[0] if fact_incidents else 0} incidents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
