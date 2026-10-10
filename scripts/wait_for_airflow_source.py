"""Wait for deterministic verification telemetry to reach typed source tables."""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from datetime import date

from netpulse_analytics.orchestration.models import DateRange
from netpulse_analytics.orchestration.repository import PostgresOrchestrationRepository


def wait_for_source(
    repository: PostgresOrchestrationRepository,
    selected: DateRange,
    *,
    timeout_seconds: float,
    interval_seconds: float = 1,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    deadline = monotonic() + timeout_seconds
    while True:
        count = repository.load_source_snapshot(selected).observation_count
        if count > 0:
            return count
        if monotonic() >= deadline:
            raise TimeoutError("typed source observations did not arrive before timeout")
        sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    selected = DateRange(args.date, args.date)
    database_url = (
        os.environ.get("NETPULSE_ADMIN_DATABASE_URL") or os.environ["NETPULSE_DATABASE_URL"]
    )
    count = wait_for_source(
        PostgresOrchestrationRepository(database_url),
        selected,
        timeout_seconds=args.timeout,
    )
    print(f"Source window ready: {count} typed observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
