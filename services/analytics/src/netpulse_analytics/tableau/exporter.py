"""CSV rendering and atomic directory publication for Tableau exports."""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from contextlib import suppress
from pathlib import Path

from netpulse_analytics.tableau.models import ExportBundle

EXPECTED_FILES = {
    "agent_performance.csv",
    "daily_reliability.csv",
    "incidents.csv",
    "pipeline_health.csv",
}


def _validate_bundle(bundle: ExportBundle) -> None:
    if set(bundle.datasets) != EXPECTED_FILES:
        raise ValueError("Tableau export must contain exactly four expected CSV files")


def _validate_output_path(output_dir: Path) -> Path:
    output = output_dir.absolute()
    if output_dir.is_symlink():
        raise ValueError("output directory cannot be a symbolic link")
    if output == Path(output.anchor):
        raise ValueError("output directory cannot be the filesystem root")
    if output.resolve(strict=False) == Path.cwd().resolve():
        raise ValueError("output directory cannot be the current working directory")
    if output.exists() and not output.is_dir():
        raise ValueError("output directory path is not a directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _write_staging(bundle: ExportBundle, staging_dir: Path) -> None:
    for filename, dataset in bundle.datasets.items():
        with (staging_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(dataset.columns)
            writer.writerows(dataset.rows)


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _swap_directories(staging_dir: Path, output_dir: Path) -> None:
    backup_dir: Path | None = None
    if output_dir.exists():
        backup_dir = Path(
            tempfile.mkdtemp(dir=output_dir.parent, prefix=f".{output_dir.name}.backup.")
        )
        backup_dir.rmdir()
        os.replace(output_dir, backup_dir)
    try:
        os.replace(staging_dir, output_dir)
    except BaseException:
        if backup_dir is not None:
            os.replace(backup_dir, output_dir)
        raise
    if backup_dir is not None:
        with suppress(OSError):
            _remove_tree(backup_dir)


def publish_export(bundle: ExportBundle, output_dir: Path) -> None:
    _validate_bundle(bundle)
    output = _validate_output_path(output_dir)
    staging_dir = Path(tempfile.mkdtemp(dir=output.parent, prefix=f".{output.name}.staging."))
    try:
        _write_staging(bundle, staging_dir)
        _swap_directories(staging_dir, output)
    finally:
        with suppress(OSError):
            _remove_tree(staging_dir)
