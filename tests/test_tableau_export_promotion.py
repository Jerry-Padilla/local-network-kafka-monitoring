from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import promote_tableau_export

EXPECTED_FILES = {
    "daily_reliability.csv",
    "incidents.csv",
    "agent_performance.csv",
    "pipeline_health.csv",
}


def _stage_complete_export(output_dir: Path) -> None:
    staged = output_dir / ".next"
    staged.mkdir(parents=True)
    for filename in EXPECTED_FILES:
        (staged / filename).write_text(f"{filename}\n", encoding="utf-8")


def test_promote_staged_export_replaces_the_host_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    (output_dir / "previous.csv").write_text("previous\n", encoding="utf-8")
    _stage_complete_export(output_dir)

    promote_tableau_export.promote_staged_export(output_dir)

    assert {path.name for path in output_dir.iterdir()} == EXPECTED_FILES
    assert not list(tmp_path.glob(".tableau_exports.*"))


def test_promote_staged_export_rejects_an_incomplete_bundle(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _stage_complete_export(output_dir)
    (output_dir / ".next" / "incidents.csv").unlink()

    with pytest.raises(ValueError, match="exactly four expected CSV files"):
        promote_tableau_export.promote_staged_export(output_dir)

    assert (output_dir / ".next").is_dir()


def test_promotion_failure_restores_the_previous_host_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    marker = output_dir / "previous.csv"
    marker.write_text("previous\n", encoding="utf-8")
    _stage_complete_export(output_dir)
    real_replace = os.replace
    calls = 0

    def fail_final_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("host publication failed")
        real_replace(source, destination)

    monkeypatch.setattr(promote_tableau_export.os, "replace", fail_final_replace)

    with pytest.raises(OSError, match="host publication failed"):
        promote_tableau_export.promote_staged_export(output_dir)

    assert marker.read_text(encoding="utf-8") == "previous\n"
    assert not list(tmp_path.glob(".tableau_exports.*"))
