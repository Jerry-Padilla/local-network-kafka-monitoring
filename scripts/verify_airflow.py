"""Verify a successful, reconciled, idempotently rerun Airflow analytics window."""

from __future__ import annotations

import argparse
import os
from datetime import date

import psycopg
from netpulse_analytics.orchestration.models import DateRange
from netpulse_analytics.orchestration.repository import PostgresOrchestrationRepository
from netpulse_analytics.orchestration.selection import orchestration_run_key


def _require_successful_rerun(row: tuple[object, ...], minimum_attempts: int) -> int:
    status, attempt_count, analytics_run_id, daily_mismatches, incident_mismatches = row
    if status != "success":
        raise RuntimeError(f"Airflow workflow status is {status!r}, expected 'success'")
    if int(attempt_count) < minimum_attempts:
        raise RuntimeError(
            f"Airflow workflow has {attempt_count} attempt(s), expected {minimum_attempts}"
        )
    if analytics_run_id is None:
        raise RuntimeError("Airflow workflow did not record an analytics run")
    if int(daily_mismatches) or int(incident_mismatches):
        raise RuntimeError("Airflow workflow recorded reconciliation mismatches")
    return int(analytics_run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--through-date", type=date.fromisoformat, required=True)
    parser.add_argument("--minimum-attempts", type=int, default=2)
    args = parser.parse_args()
    if args.minimum_attempts < 2:
        raise ValueError("minimum attempts must be at least two")

    database_url = (
        os.environ.get("NETPULSE_ADMIN_DATABASE_URL") or os.environ["NETPULSE_DATABASE_URL"]
    )
    selected = DateRange(args.from_date, args.through_date)
    run_key = orchestration_run_key("netpulse_daily_reliability", selected)
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """SELECT status, attempt_count, analytics_run_id,
                      daily_mismatch_rows, incident_mismatch_rows
               FROM analytics_orchestration_runs
               WHERE run_key = %s""",
            (run_key,),
        ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"expected one idempotent Airflow run row, found {len(rows)}")
    analytics_run_id = _require_successful_rerun(rows[0], args.minimum_attempts)

    repository = PostgresOrchestrationRepository(database_url)
    reconciliation = repository.reconcile(selected)
    reconciliation.require_valid()
    if reconciliation.daily_source_rows <= 0 or reconciliation.daily_fact_rows <= 0:
        raise RuntimeError("Airflow verification window did not produce daily analytics facts")
    reporting = repository.validate_reporting(selected, analytics_run_id)
    reporting.require_valid()
    print(
        "Airflow verification passed: "
        f"{reconciliation.daily_fact_rows} daily grains, "
        f"{args.minimum_attempts}+ idempotent attempts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
