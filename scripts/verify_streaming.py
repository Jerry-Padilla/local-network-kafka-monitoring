"""Verify Phase 3 curated storage against a running PostgreSQL service."""

from __future__ import annotations

import os
import sys

import psycopg


def main() -> int:
    database_url = os.getenv(
        "NETPULSE_DATABASE_URL",
        "postgresql://netpulse_app:change-me-local-app@postgres:5432/netpulse",
    )
    failures: list[str] = []
    with psycopg.connect(database_url) as connection:
        metric_count = _scalar(connection, "SELECT count(*) FROM network_window_metrics")
        failure_count = _scalar(
            connection,
            "SELECT count(*) FROM stream_processing_failures",
        )
        duplicate_count = _scalar(
            connection,
            """
            SELECT count(*)
            FROM (
                SELECT
                    window_start,
                    window_end,
                    window_size_seconds,
                    agent_id,
                    target_id,
                    measurement_type
                FROM network_window_metrics
                GROUP BY 1, 2, 3, 4, 5, 6
                HAVING count(*) > 1
            ) duplicates
            """,
        )
        window_sizes = {
            int(row[0])
            for row in connection.execute(
                "SELECT DISTINCT window_size_seconds FROM network_window_metrics"
            ).fetchall()
        }
        agents = {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT agent_id FROM network_window_metrics"
            ).fetchall()
        }

    print(f"curated window metrics: {metric_count}")
    print(f"stream processing failures: {failure_count}")
    print(f"duplicate aggregate keys: {duplicate_count}")
    print(f"window sizes: {sorted(window_sizes)}")
    print(f"agents: {sorted(agents)}")

    if metric_count < 1:
        failures.append("network_window_metrics was empty")
    if failure_count < 1:
        failures.append("stream_processing_failures was empty")
    if duplicate_count != 0:
        failures.append("duplicate aggregate keys were present")
    if window_sizes != {60, 300, 900, 86_400}:
        failures.append("not all configured event-time windows were present")
    expected_agents = {"network-agent-ethernet-01", "network-agent-wifi-01"}
    if not expected_agents.issubset(agents):
        failures.append("both simulated agents were not present")

    if failures:
        for failure in failures:
            print(f"FAILED: {failure}", file=sys.stderr)
        return 1
    print("Phase 3 streaming invariants passed")
    return 0


def _scalar(connection: psycopg.Connection[tuple[object, ...]], query: str) -> int:
    row = connection.execute(query).fetchone()
    return int(row[0]) if row else 0


if __name__ == "__main__":
    raise SystemExit(main())
