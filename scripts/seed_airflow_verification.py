"""Seed a deterministic Airflow verification window through ingestion persistence."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime

from netpulse_contracts.validation import validate_event
from netpulse_ingestion.processor_types import SourceRecord
from netpulse_ingestion.repository import PostgresEventRepository
from netpulse_simulator.scenarios import ScenarioGenerator, SimulatedRecord

STARTED = datetime(2035, 1, 15, 12, tzinfo=UTC)


def seed_records(
    repository: PostgresEventRepository,
    records: Sequence[SimulatedRecord],
    started: datetime,
) -> int:
    first_offset = int(started.timestamp()) * 100
    inserted = 0
    for index, record in enumerate(records):
        event = validate_event(record.value)
        source = SourceRecord(
            topic=record.topic,
            partition=99,
            offset=first_offset + index,
            key=record.key,
            value=record.value,
        )
        inserted += int(repository.persist_event(event, source))
    return inserted


def main() -> int:
    records = ScenarioGenerator(seed=4209).generate_round("healthy", STARTED)
    repository = PostgresEventRepository(os.environ["NETPULSE_DATABASE_URL"])
    repository.open()
    try:
        inserted = seed_records(repository, records, STARTED)
    finally:
        repository.close()
    print(f"Airflow verification fixture ready: {inserted} new of {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
