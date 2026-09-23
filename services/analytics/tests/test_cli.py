from datetime import date

import pytest
from netpulse_analytics.cli import parse_selection


def test_all_and_inclusive_range() -> None:
    assert parse_selection(["--all"]).is_all
    selected = parse_selection(["--from-date", "2026-09-20", "--through-date", "2026-09-21"])
    assert (selected.from_date, selected.through_date, selected.is_all) == (
        date(2026, 9, 20),
        date(2026, 9, 21),
        False,
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--from-date", "2026-09-20"],
        ["--through-date", "2026-09-20"],
        ["--from-date", "2026-09-21", "--through-date", "2026-09-20"],
        ["--all", "--from-date", "2026-09-20", "--through-date", "2026-09-21"],
        ["--from-date", "2026-02-30", "--through-date", "2026-03-01"],
    ],
)
def test_invalid_selection_fails_before_connection(args: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_selection(args)
