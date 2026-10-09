"""Typed contracts shared by Airflow tasks and analytics validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class DateRange:
    from_date: date
    through_date: date

    def __post_init__(self) -> None:
        if self.from_date > self.through_date:
            raise ValueError("analytics date range must be ordered")

    @property
    def day_count(self) -> int:
        return (self.through_date - self.from_date).days + 1

    @property
    def start(self) -> datetime:
        return datetime.combine(self.from_date, time.min, tzinfo=UTC)

    @property
    def end(self) -> datetime:
        return datetime.combine(self.through_date + timedelta(days=1), time.min, tzinfo=UTC)


class SourceStatus(StrEnum):
    HEALTHY = "healthy"
    DELAYED = "delayed"
    LEGITIMATELY_EMPTY = "legitimately_empty"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"


def _validate_timestamp(value: datetime | None) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("source timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    observation_count: int
    relevant_raw_count: int
    heartbeat_count: int
    invalid_count: int
    latest_observation_at: datetime | None
    latest_heartbeat_at: datetime | None
    maximum_ingestion_delay_seconds: float | None

    def __post_init__(self) -> None:
        counts = (
            self.observation_count,
            self.relevant_raw_count,
            self.heartbeat_count,
            self.invalid_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("source counts must be nonnegative")
        if (
            self.maximum_ingestion_delay_seconds is not None
            and self.maximum_ingestion_delay_seconds < 0
        ):
            raise ValueError("ingestion delay must be nonnegative")
        _validate_timestamp(self.latest_observation_at)
        _validate_timestamp(self.latest_heartbeat_at)


@dataclass(frozen=True, slots=True)
class SourceAssessment:
    status: SourceStatus
    snapshot: SourceSnapshot
    reason: str

    @property
    def may_refresh(self) -> bool:
        return self.status in {
            SourceStatus.HEALTHY,
            SourceStatus.DELAYED,
            SourceStatus.LEGITIMATELY_EMPTY,
        }
