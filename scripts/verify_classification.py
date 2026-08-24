"""Verify deterministic Phase 4 lifecycle and durable publication invariants."""

from __future__ import annotations

import os

import psycopg


def main() -> int:
    database_url = os.getenv(
        "NETPULSE_DATABASE_URL",
        "postgresql://netpulse_app:change-me-local-app@postgres:5432/netpulse",
    )
    with psycopg.connect(database_url) as connection:
        incident = connection.execute(
            """
            SELECT status, positive_observations, recovery_observations, end_time
            FROM network_incidents
            WHERE incident_type = 'wifi_degradation'
            ORDER BY start_time DESC
            LIMIT 1
            """
        ).fetchone()
        pending = connection.execute(
            "SELECT COUNT(*) FROM incident_state_events WHERE published_at IS NULL"
        ).fetchone()
        states = connection.execute(
            """
            SELECT ARRAY_AGG(status ORDER BY state_revision)
            FROM incident_state_events
            WHERE incident_id = (
                SELECT incident_id
                FROM network_incidents
                WHERE incident_type = 'wifi_degradation'
                ORDER BY start_time DESC
                LIMIT 1
            )
            """
        ).fetchone()

    errors: list[str] = []
    if incident is None:
        errors.append("no wifi_degradation incident was persisted")
    elif incident[0] != "resolved" or incident[3] is None:
        errors.append(f"latest wifi_degradation incident is not resolved: {incident!r}")
    if pending is None or int(pending[0]) != 0:
        errors.append(f"incident outbox contains pending records: {pending!r}")
    observed_states = [] if states is None or states[0] is None else list(states[0])
    for required in ("candidate", "open", "recovering", "resolved"):
        if required not in observed_states:
            errors.append(f"missing lifecycle state {required}: {observed_states!r}")

    if errors:
        for error in errors:
            print(f"FAILED: {error}")
        return 1
    print("Phase 4 classification invariants passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
