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
            if filename in {"daily_reliability.csv", "agent_performance.csv"}:
                writer.writerow(["value"] * len(header))
            if filename == "pipeline_health.csv":
                writer.writerow(["2035-01-15T12:00:00Z", "", "", 0, 0, "", 0, 0])


def test_verify_export_accepts_exact_bundle_with_expected_headers(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)

    assert verify_export(output_dir) == {
        "agent_performance.csv": 1,
        "daily_reliability.csv": 1,
        "incidents.csv": 0,
        "pipeline_health.csv": 1,
    }


def test_verify_export_rejects_missing_dataset(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)
    (output_dir / "incidents.csv").unlink()

    with pytest.raises(ValueError, match=r"missing.*incidents.csv"):
        verify_export(output_dir)


def test_verify_export_rejects_unexpected_header(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)
    (output_dir / "daily_reliability.csv").write_text("agent_id\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"daily_reliability.csv.*header"):
        verify_export(output_dir)


def test_verify_export_rejects_empty_seeded_analytics(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)
    header = EXPECTED_HEADERS["daily_reliability.csv"]
    (output_dir / "daily_reliability.csv").write_text(",".join(header) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"daily_reliability.csv.*at least one"):
        verify_export(output_dir)


def test_verify_export_rejects_ragged_data_row(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    _write_bundle(output_dir)
    with (output_dir / "agent_performance.csv").open("a", encoding="utf-8") as handle:
        handle.write("too,short\n")

    with pytest.raises(ValueError, match=r"agent_performance.csv.*row 3.*columns"):
        verify_export(output_dir)
