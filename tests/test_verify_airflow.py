import pytest

from scripts.verify_airflow import _require_successful_rerun


def test_verify_airflow_accepts_successful_idempotent_rerun() -> None:
    assert _require_successful_rerun(("success", 2, 41, 0, 0), 2) == 41


@pytest.mark.parametrize(
    "row",
    [
        ("failed", 2, 41, 0, 0),
        ("success", 1, 41, 0, 0),
        ("success", 2, None, 0, 0),
        ("success", 2, 41, 1, 0),
        ("success", 2, 41, 0, 1),
    ],
)
def test_verify_airflow_rejects_incomplete_or_mismatched_runs(
    row: tuple[object, ...],
) -> None:
    with pytest.raises(RuntimeError):
        _require_successful_rerun(row, 2)
