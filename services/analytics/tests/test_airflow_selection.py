from datetime import UTC, date, datetime

import pytest
from netpulse_analytics.orchestration.models import DateRange
from netpulse_analytics.orchestration.selection import orchestration_run_key, select_date_range


def test_scheduled_run_selects_previous_complete_utc_date() -> None:
    selected = select_date_range(
        data_interval_end=datetime(2026, 10, 9, 2, tzinfo=UTC),
        from_date=None,
        through_date=None,
    )

    assert selected == DateRange(date(2026, 10, 8), date(2026, 10, 8))
    assert selected.start == datetime(2026, 10, 8, tzinfo=UTC)
    assert selected.end == datetime(2026, 10, 9, tzinfo=UTC)


def test_manual_override_is_inclusive_and_bounded() -> None:
    selected = select_date_range(
        data_interval_end=None,
        from_date="2026-09-01",
        through_date="2026-10-01",
    )

    assert selected.day_count == 31


def test_orchestration_run_key_is_stable_for_the_same_logical_window() -> None:
    selected = DateRange(date(2035, 1, 15), date(2035, 1, 15))

    assert orchestration_run_key("netpulse_daily_reliability", selected) == (
        "netpulse_daily_reliability:2035-01-15:2035-01-15"
    )


@pytest.mark.parametrize(
    ("interval_end", "from_date", "through_date", "message"),
    [
        (None, None, None, "data interval end"),
        (datetime(2026, 10, 9, 2), None, None, "timezone-aware"),
        (None, "2026-10-01", None, "both manual dates"),
        (None, None, "2026-10-01", "both manual dates"),
        (None, "2026-10-02", "2026-10-01", "ordered"),
        (None, "2026-09-01", "2026-10-02", "31 days"),
        (None, "not-a-date", "2026-10-01", "ISO"),
    ],
)
def test_invalid_date_windows_fail_before_database_access(
    interval_end: datetime | None,
    from_date: str | None,
    through_date: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        select_date_range(interval_end, from_date, through_date)
