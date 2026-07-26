"""Verify Phase 1 database invariants against a running stack."""

from __future__ import annotations

import os
import sys

import psycopg


def main() -> int:
    database_url = os.getenv(
        "NETPULSE_DATABASE_URL",
        "postgresql://netpulse_app:change-me-local-app@postgres:5432/netpulse",
    )
    checks = {
        "raw events": "SELECT count(*) FROM raw_events",
        "wired agent events": (
            "SELECT count(*) FROM raw_events WHERE agent_id = 'network-agent-ethernet-01'"
        ),
        "wireless agent events": (
            "SELECT count(*) FROM raw_events WHERE agent_id = 'network-agent-wifi-01'"
        ),
        "typed measurements": "SELECT count(*) FROM network_measurements",
    }
    failures: list[str] = []
    with psycopg.connect(database_url) as connection:
        for label, query in checks.items():
            value = connection.execute(query).fetchone()
            count = int(value[0]) if value else 0
            print(f"{label}: {count}")
            if count < 1:
                failures.append(f"{label} was empty")

        duplicates = connection.execute(
            """
            SELECT count(*)
            FROM (
                SELECT event_id FROM raw_events GROUP BY event_id HAVING count(*) > 1
            ) duplicate_ids
            """
        ).fetchone()
        duplicate_count = int(duplicates[0]) if duplicates else -1
        print(f"duplicate event IDs: {duplicate_count}")
        if duplicate_count != 0:
            failures.append("raw_events contains duplicate event IDs")

    if failures:
        for failure in failures:
            print(f"FAILED: {failure}", file=sys.stderr)
        return 1
    print("Phase 1 database invariants passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
