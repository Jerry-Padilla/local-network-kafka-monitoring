from pathlib import Path

import pytest
from netpulse_analytics.config import TableauExportConfig
from netpulse_analytics.tableau.models import CsvDataset, TableauSnapshot


def test_tableau_config_uses_existing_database_url_and_explicit_output_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql://local@localhost/netpulse"
    output_dir = Path("tableau_exports")
    monkeypatch.setenv("NETPULSE_DATABASE_URL", database_url)

    config = TableauExportConfig.from_env(output_dir)

    assert config.database_url == database_url
    assert config.output_dir == output_dir


def test_tableau_config_rejects_missing_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NETPULSE_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="NETPULSE_DATABASE_URL"):
        TableauExportConfig.from_env(Path("tableau_exports"))


def test_csv_dataset_rejects_rows_with_the_wrong_width() -> None:
    with pytest.raises(ValueError, match="column count"):
        CsvDataset(columns=("one", "two"), rows=((1,),))


def test_snapshot_defaults_to_empty_daily_and_incident_rows() -> None:
    snapshot = TableauSnapshot()

    assert snapshot.daily_reliability == ()
    assert snapshot.incidents == ()
    assert snapshot.pipeline_health is None
