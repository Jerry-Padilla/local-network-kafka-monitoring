"""Classify source windows without mutating operational data."""

from __future__ import annotations

from datetime import timedelta

from netpulse_analytics.orchestration.models import (
    SourceAssessment,
    SourceSnapshot,
    SourceStatus,
)


def assess_source_quality(
    snapshot: SourceSnapshot,
    *,
    stale_after: timedelta,
    delay_after: timedelta,
) -> SourceAssessment:
    if stale_after <= timedelta(0) or delay_after <= timedelta(0):
        raise ValueError("quality thresholds must be positive")
    if snapshot.invalid_count:
        return SourceAssessment(SourceStatus.INVALID, snapshot, "invalid source records exist")
    if snapshot.observation_count == 0:
        if snapshot.relevant_raw_count or snapshot.heartbeat_count:
            return SourceAssessment(
                SourceStatus.MISSING,
                snapshot,
                "upstream activity exists without typed probe observations",
            )
        return SourceAssessment(
            SourceStatus.LEGITIMATELY_EMPTY,
            snapshot,
            "no upstream activity exists in the requested window",
        )
    if snapshot.latest_observation_at is None or (
        snapshot.latest_heartbeat_at is None and snapshot.heartbeat_count > 0
    ):
        raise ValueError("positive source counts require corresponding timestamps")
    if (
        snapshot.latest_heartbeat_at is not None
        and snapshot.latest_observation_at is not None
        and snapshot.latest_heartbeat_at - snapshot.latest_observation_at > stale_after
    ):
        return SourceAssessment(
            SourceStatus.STALE,
            snapshot,
            "agent activity continued after probe observations became stale",
        )
    if (
        snapshot.maximum_ingestion_delay_seconds is not None
        and snapshot.maximum_ingestion_delay_seconds > delay_after.total_seconds()
    ):
        return SourceAssessment(
            SourceStatus.DELAYED,
            snapshot,
            "observations arrived after the configured ingestion grace",
        )
    return SourceAssessment(SourceStatus.HEALTHY, snapshot, "source observations are current")
