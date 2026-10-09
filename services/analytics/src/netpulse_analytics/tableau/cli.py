"""Command-line interface for Tableau CSV exports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg

from netpulse_analytics.config import TableauExportConfig
from netpulse_analytics.tableau.service import export_tableau


def parse_args(argv: list[str] | None) -> Path:
    parser = argparse.ArgumentParser(description="Export NetPulse reporting data for Tableau")
    parser.add_argument("--output-dir", type=Path, default=Path("tableau_exports"))
    return parser.parse_args(argv).output_dir


def main(argv: list[str] | None = None) -> int:
    output_dir = parse_args(argv)
    try:
        config = TableauExportConfig.from_env(output_dir)
        summary = export_tableau(config)
    except (ValueError, psycopg.Error, OSError, RuntimeError) as error:
        print(
            json.dumps(
                {
                    "event": "tableau_export_failed",
                    "error_type": type(error).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "event": "tableau_export_completed",
                "output_dir": str(summary.output_dir),
                "row_counts": dict(summary.row_counts),
            },
            sort_keys=True,
        )
    )
    return 0
