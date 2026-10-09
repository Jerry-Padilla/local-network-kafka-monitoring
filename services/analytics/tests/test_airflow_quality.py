from datetime import UTC, datetime, timedelta

import pytest
from netpulse_analytics.orchestration.models import SourceSnapshot, SourceStatus
from netpulse_analytics.orchestration.quality import assess_source_quality

NOW = datetime(2026, 10, 9, tzinfo=UTC)


def _snapshot(**overrides: object) -> SourceSnapshot:
    values: dict[str, object] = {
        "observation_count": 10,
        "relevant_raw_count": 10,
        "heartbeat_count": 2,
        "invalid_count": 0,
        "latest_observation_at": NOW - timedelta(minutes=2),
        "latest_heartbeat_at": NOW - timedelta(minutes=1),
        "maximum_ingestion_delay_seconds": 2.0,
    }
    values.update(overrides)
    return SourceSnapshot(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (_snapshot(), SourceStatus.HEALTHY),
        (
            _snapshot(maximum_ingestion_delay_seconds=601.0),
            SourceStatus.DELAYED,
        ),
        (
            _snapshot(
                observation_count=0,
                relevant_raw_count=0,
                heartbeat_count=0,
                latest_observation_at=None,
                latest_heartbeat_at=None,
                maximum_ingestion_delay_seconds=None,
            ),
            SourceStatus.LEGITIMATELY_EMPTY,
        ),
        (
            _snapshot(observation_count=0, latest_observation_at=None),
            SourceStatus.MISSING,
        ),
        (
            _snapshot(latest_observation_at=NOW - timedelta(hours=2)),
            SourceStatus.STALE,
        ),
        (_snapshot(invalid_count=1), SourceStatus.INVALID),
    ],
)
def test_source_quality_classifies_distinct_operational_states(
    snapshot: SourceSnapshot,
    expected: SourceStatus,
) -> None:
    assessment = assess_source_quality(
        snapshot,
        stale_after=timedelta(minutes=15),
        delay_after=timedelta(minutes=10),
    )

    assert assessment.status is expected
    assert assessment.may_refresh is (expected in {
        SourceStatus.HEALTHY,
        SourceStatus.DELAYED,
        SourceStatus.LEGITIMATELY_EMPTY,
    })


def test_source_snapshot_rejects_negative_counts_and_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        _snapshot(observation_count=-1)
    with pytest.raises(ValueError, match="timezone-aware"):
        _snapshot(latest_observation_at=datetime(2026, 10, 9))
