from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.verify_tableau_export import EXPECTED_HEADERS, verify_export


def _write_bundle(output_dir: Path) -> None:
    output_dir.mkdir()
    for filename, header in EXPECTED_HEADERS.items():
        with (output_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            if filename == "pipeline_health.csv":
                writer.writerow(["2035-01-15T12:00:00Z", "", "", 0, 0, "", 0, 0])


def test_verify_export_accepts_exact_bundle_with_expected_headers(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)

    assert verify_export(output_dir) == {
        "agent_performance.csv": 0,
        "daily_reliability.csv": 0,
        "incidents.csv": 0,
        "pipeline_health.csv": 1,
    }


def test_verify_export_rejects_missing_dataset(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)
    (output_dir / "incidents.csv").unlink()

    with pytest.raises(ValueError, match="missing.*incidents.csv"):
        verify_export(output_dir)


def test_verify_export_rejects_unexpected_header(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)
    (output_dir / "daily_reliability.csv").write_text("agent_id\n", encoding="utf-8")

    with pytest.raises(ValueError, match="daily_reliability.csv.*header"):
        verify_export(output_dir)
