"""Resolve bounded UTC analytics ranges from Airflow scheduling inputs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from netpulse_analytics.orchestration.models import DateRange


def orchestration_run_key(dag_id: str, selected: DateRange) -> str:
    if not dag_id.strip():
        raise ValueError("DAG id is required for the orchestration run key")
    return f"{dag_id}:{selected.from_date.isoformat()}:{selected.through_date.isoformat()}"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("manual dates must use ISO YYYY-MM-DD format") from error


def select_date_range(
    data_interval_end: datetime | None,
    from_date: str | None,
    through_date: str | None,
    *,
    maximum_days: int = 31,
) -> DateRange:
    if (from_date is None) != (through_date is None):
        raise ValueError("provide both manual dates or neither")
    if from_date is not None and through_date is not None:
        selected = DateRange(_parse_date(from_date), _parse_date(through_date))
    else:
        if data_interval_end is None:
            raise ValueError("data interval end is required without manual dates")
        if data_interval_end.tzinfo is None or data_interval_end.utcoffset() is None:
            raise ValueError("data interval end must be timezone-aware")
        target = data_interval_end.astimezone(UTC).date() - timedelta(days=1)
        selected = DateRange(target, target)
    if selected.day_count > maximum_days:
        raise ValueError(f"analytics range cannot exceed {maximum_days} days")
    return selected
