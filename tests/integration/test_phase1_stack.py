from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from netpulse_simulator.config import SimulatorConfig
from netpulse_simulator.publisher import KafkaPublisher
from netpulse_simulator.scenarios import ScenarioGenerator

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.getenv("NETPULSE_INTEGRATION") == "1"


def _wait_for_count(
    database_url: str,
    table: str,
    minimum: int,
    where: str | None = None,
    timeout: float = 20,
) -> int:
    deadline = time.monotonic() + timeout
    query = f"SELECT count(*) FROM {table}"
    if where is not None:
        query = f"{query} WHERE {where}"
    while time.monotonic() < deadline:
        with psycopg.connect(database_url) as connection:
            row = connection.execute(query).fetchone()
            count = int(row[0]) if row else 0
        if count >= minimum:
            return count
        time.sleep(0.5)
    raise AssertionError(f"{table} did not reach {minimum} rows within {timeout} seconds")


@pytest.mark.skipif(not _integration_enabled(), reason="set NETPULSE_INTEGRATION=1")
def test_valid_invalid_and_duplicate_paths() -> None:
    database_url = os.environ["NETPULSE_DATABASE_URL"]
    config = SimulatorConfig.from_env()
    generator = ScenarioGenerator(seed=101)
    publisher = KafkaPublisher(config)

    with psycopg.connect(database_url) as connection:
        baseline_raw = int(connection.execute("SELECT count(*) FROM raw_events").fetchone()[0])
        baseline_failures = int(
            connection.execute("SELECT count(*) FROM processing_failures").fetchone()[0]
        )
        baseline_dead_letters = int(
            connection.execute(
                """
                SELECT count(*) FROM processing_failures
                WHERE dead_letter_published_at IS NOT NULL
                """
            ).fetchone()[0]
        )

    run_time = datetime.now(UTC)
    duplicate_records = generator.generate_round("duplicate-events", run_time)
    duplicate_event_id = __import__("json").loads(duplicate_records[0].value)["event_id"]
    malformed_records = generator.generate_round(
        "malformed-events", run_time + timedelta(minutes=1)
    )
    try:
        publisher.publish_batch(duplicate_records + malformed_records)
    finally:
        publisher.close()

    _wait_for_count(database_url, "raw_events", baseline_raw + 2)
    _wait_for_count(database_url, "processing_failures", baseline_failures + 1)
    _wait_for_count(
        database_url,
        "processing_failures",
        baseline_dead_letters + 1,
        "dead_letter_published_at IS NOT NULL",
    )

    with psycopg.connect(database_url) as connection:
        duplicate_count = int(
            connection.execute(
                "SELECT count(*) FROM raw_events WHERE event_id = %s",
                (duplicate_event_id,),
            ).fetchone()[0]
        )
        dlq_marked = int(
            connection.execute(
                """
                SELECT count(*) FROM processing_failures
                WHERE dead_letter_published_at IS NOT NULL
                """
            ).fetchone()[0]
        )

    assert duplicate_count == 1
    assert dlq_marked >= baseline_dead_letters + 1
