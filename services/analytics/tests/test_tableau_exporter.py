from __future__ import annotations

import os
from pathlib import Path

import pytest
from netpulse_analytics.tableau import exporter
from netpulse_analytics.tableau.exporter import _validate_output_path, publish_export
from netpulse_analytics.tableau.models import CsvDataset, ExportBundle


def _bundle() -> ExportBundle:
    return ExportBundle(
        datasets={
            "daily_reliability.csv": CsvDataset(
                columns=("date_utc", "total_probes", "average_latency_ms"),
                rows=(("2026-10-08", 10, None),),
            ),
            "incidents.csv": CsvDataset(columns=("incident_id",), rows=()),
            "agent_performance.csv": CsvDataset(
                columns=("agent_key", "success_rate_pct"),
                rows=(("agent_4d61eabb2c3e", 99.5),),
            ),
            "pipeline_health.csv": CsvDataset(
                columns=("observed_at_utc",),
                rows=(("2026-10-08T02:00:00Z",),),
            ),
        }
    )


def _read_exact(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def test_publish_export_writes_exact_headers_utf8_lf_and_empty_null_fields(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "tableau_exports"

    publish_export(_bundle(), output_dir)

    daily = _read_exact(output_dir / "daily_reliability.csv")
    assert daily == ("date_utc,total_probes,average_latency_ms\n2026-10-08,10,\n")
    assert b"\r\n" not in (output_dir / "daily_reliability.csv").read_bytes()


def test_publish_export_creates_all_four_csvs_for_empty_datasets(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    bundle = ExportBundle(
        datasets={
            "daily_reliability.csv": CsvDataset(("date_utc",), ()),
            "incidents.csv": CsvDataset(("incident_id",), ()),
            "agent_performance.csv": CsvDataset(("agent_key",), ()),
            "pipeline_health.csv": CsvDataset(("observed_at_utc",), ()),
        }
    )

    publish_export(bundle, output_dir)

    assert {path.name for path in output_dir.iterdir()} == set(bundle.datasets)
    assert _read_exact(output_dir / "incidents.csv") == "incident_id\n"


@pytest.mark.parametrize(
    "datasets",
    [
        {},
        {"../escaped.csv": CsvDataset(("value",), (("unsafe",),))},
    ],
)
def test_publish_export_rejects_bundles_outside_the_four_file_contract(
    tmp_path: Path,
    datasets: dict[str, CsvDataset],
) -> None:
    with pytest.raises(ValueError, match="exactly four expected CSV files"):
        publish_export(ExportBundle(datasets=datasets), tmp_path / "tableau_exports")

    assert not (tmp_path / "escaped.csv").exists()


def test_publish_export_replaces_a_complete_previous_export(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    (output_dir / "old.csv").write_text("stale\n", encoding="utf-8")

    publish_export(_bundle(), output_dir)

    assert not (output_dir / "old.csv").exists()
    assert {path.name for path in output_dir.iterdir()} == set(_bundle().datasets)


def test_staging_write_failure_preserves_previous_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    marker = output_dir / "valid.csv"
    marker.write_bytes(b"previous-valid-export\n")

    def fail_write(_bundle: ExportBundle, _staging: Path) -> None:
        raise RuntimeError("staging failed")

    monkeypatch.setattr(exporter, "_write_staging", fail_write)

    with pytest.raises(RuntimeError, match="staging failed"):
        publish_export(_bundle(), output_dir)

    assert marker.read_bytes() == b"previous-valid-export\n"


def _fail_second_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    real_replace = os.replace
    calls = 0

    def fail_second(source: str | Path, destination: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("new export rename failed")
        real_replace(source, destination)

    monkeypatch.setattr(exporter.os, "replace", fail_second)


def test_second_rename_failure_restores_previous_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    marker = output_dir / "valid.csv"
    marker.write_bytes(b"previous-valid-export\n")
    _fail_second_replace(monkeypatch)

    with pytest.raises(OSError, match="new export rename failed"):
        publish_export(_bundle(), output_dir)

    assert marker.read_bytes() == b"previous-valid-export\n"


def test_database_independent_publication_never_leaves_backup_as_active_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    (output_dir / "valid.csv").write_text("previous\n", encoding="utf-8")
    _fail_second_replace(monkeypatch)

    with pytest.raises(OSError):
        publish_export(_bundle(), output_dir)

    assert output_dir.is_dir()
    assert not list(tmp_path.glob(".tableau_exports.backup.*"))
    assert not list(tmp_path.glob(".tableau_exports.staging.*"))


def test_rejects_filesystem_root_current_directory_symlink_and_regular_file(
    tmp_path: Path,
) -> None:
    regular_file = tmp_path / "output.csv"
    regular_file.write_text("not a directory", encoding="utf-8")
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    symlink = tmp_path / "linked-output"
    try:
        symlink.symlink_to(real_directory, target_is_directory=True)
    except OSError:
        symlink = None

    dangerous = [Path.cwd().anchor and Path(Path.cwd().anchor), Path.cwd(), regular_file]
    if symlink is not None:
        dangerous.append(symlink)

    for path in dangerous:
        with pytest.raises(ValueError, match="output directory"):
            _validate_output_path(path)


def test_cleanup_failure_does_not_mask_the_primary_publication_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(_bundle: ExportBundle, _staging: Path) -> None:
        raise RuntimeError("primary publication failure")

    def fail_cleanup(_path: Path) -> None:
        raise OSError("cleanup failure")

    monkeypatch.setattr(exporter, "_write_staging", fail_write)
    monkeypatch.setattr(exporter, "_remove_tree", fail_cleanup)

    with pytest.raises(RuntimeError, match="primary publication failure"):
        publish_export(_bundle(), tmp_path / "tableau_exports")
