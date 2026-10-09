"""Atomically promote a Tableau bundle created inside the Docker bind mount."""

from __future__ import annotations

import argparse
import os
import shutil
import uuid
from contextlib import suppress
from pathlib import Path

EXPECTED_FILES = {
    "daily_reliability.csv",
    "incidents.csv",
    "agent_performance.csv",
    "pipeline_health.csv",
}


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def promote_staged_export(output_dir: Path) -> None:
    """Replace *output_dir* with its complete ``.next`` child directory."""
    output = output_dir.absolute()
    staged = output / ".next"
    if output.is_symlink() or not staged.is_dir() or staged.is_symlink():
        raise ValueError("staged Tableau export must be a real directory")
    if {path.name for path in staged.iterdir()} != EXPECTED_FILES:
        raise ValueError("staged Tableau export must contain exactly four expected CSV files")

    token = uuid.uuid4().hex
    incoming = output.parent / f".{output.name}.incoming.{token}"
    backup = output.parent / f".{output.name}.backup.{token}"
    os.replace(staged, incoming)
    moved_previous = False
    try:
        os.replace(output, backup)
        moved_previous = True
        try:
            os.replace(incoming, output)
        except BaseException:
            os.replace(backup, output)
            moved_previous = False
            raise
    finally:
        with suppress(OSError):
            _remove_tree(incoming)
        if moved_previous:
            with suppress(OSError):
                _remove_tree(backup)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    promote_staged_export(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
