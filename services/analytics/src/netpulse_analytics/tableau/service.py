"""Application service for a complete Tableau export run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from netpulse_analytics.config import TableauExportConfig
from netpulse_analytics.tableau.exporter import publish_export
from netpulse_analytics.tableau.repository import PostgresTableauRepository
from netpulse_analytics.tableau.transform import build_export_bundle


@dataclass(frozen=True, slots=True)
class ExportSummary:
    output_dir: Path
    row_counts: Mapping[str, int]


def export_tableau(
    config: TableauExportConfig,
    repository: PostgresTableauRepository | None = None,
) -> ExportSummary:
    source = repository or PostgresTableauRepository(config.database_url)
    snapshot = source.load_snapshot()
    bundle = build_export_bundle(snapshot)
    publish_export(bundle, config.output_dir)
    return ExportSummary(
        output_dir=config.output_dir.absolute(),
        row_counts={name: len(dataset.rows) for name, dataset in bundle.datasets.items()},
    )
