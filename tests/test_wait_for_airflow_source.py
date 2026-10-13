from datetime import date

import pytest
from netpulse_analytics.orchestration.models import DateRange, SourceSnapshot

from scripts.wait_for_airflow_source import wait_for_source


class Repository:
    def __init__(self, counts: list[int]) -> None:
        self._counts = iter(counts)

    def load_source_snapshot(self, _selected: DateRange) -> SourceSnapshot:
        count = next(self._counts)
        return SourceSnapshot(count, count, 0, 0, None, None, None)


def test_wait_for_source_polls_until_typed_observations_arrive() -> None:
    ticks = iter([0, 0, 1, 2])
    sleeps: list[float] = []

    count = wait_for_source(
        Repository([0, 0, 4]),  # type: ignore[arg-type]
        DateRange(date(2035, 1, 15), date(2035, 1, 15)),
        timeout_seconds=5,
        monotonic=lambda: next(ticks),
        sleep=sleeps.append,
    )

    assert count == 4
    assert sleeps == [1, 1]


def test_wait_for_source_times_out_when_window_stays_empty() -> None:
    ticks = iter([0, 0, 2])
    with pytest.raises(TimeoutError, match="did not arrive"):
        wait_for_source(
            Repository([0, 0]),  # type: ignore[arg-type]
            DateRange(date(2035, 1, 15), date(2035, 1, 15)),
            timeout_seconds=1,
            monotonic=lambda: next(ticks),
            sleep=lambda _seconds: None,
        )
