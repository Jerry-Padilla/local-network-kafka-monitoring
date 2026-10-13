from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from netpulse_analytics.config import TableauExportConfig
from netpulse_analytics.tableau import cli
from netpulse_analytics.tableau.cli import main, parse_args
from netpulse_analytics.tableau.models import TableauSnapshot
from netpulse_analytics.tableau.service import ExportSummary, export_tableau


class FakeRepository:
    def __init__(self, snapshot: TableauSnapshot) -> None:
        self.snapshot = snapshot
        self.load_calls = 0

    def load_snapshot(self) -> TableauSnapshot:
        self.load_calls += 1
        return self.snapshot


def test_export_service_loads_transforms_and_publishes_once(tmp_path: Path) -> None:
    output_dir = tmp_path / "tableau_exports"
    repository = FakeRepository(TableauSnapshot())
    config = TableauExportConfig("postgresql://unused", output_dir)

    result = export_tableau(config, repository=repository)

    assert repository.load_calls == 1
    assert result.output_dir == output_dir.absolute()
    assert result.row_counts == {
        "daily_reliability.csv": 0,
        "incidents.csv": 0,
        "agent_performance.csv": 0,
        "pipeline_health.csv": 0,
    }
    assert {path.name for path in output_dir.iterdir()} == set(result.row_counts)


def test_cli_defaults_to_tableau_exports_and_accepts_output_dir() -> None:
    assert parse_args([]) == Path("tableau_exports")
    assert parse_args(["--output-dir", "custom/tableau"]) == Path("custom/tableau")


def test_cli_reports_successful_row_counts_without_sensitive_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "sentinel-password"
    monkeypatch.setenv("NETPULSE_DATABASE_URL", f"postgresql://reader:{secret}@localhost/netpulse")
    monkeypatch.setattr(
        cli,
        "export_tableau",
        lambda config: ExportSummary(
            output_dir=config.output_dir.absolute(),
            row_counts={"daily_reliability.csv": 3},
        ),
    )

    result = main(["--output-dir", "tableau_exports"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"daily_reliability.csv": 3' in captured.out
    assert secret not in captured.out + captured.err


def test_missing_database_configuration_returns_nonzero_without_touching_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "tableau_exports"
    monkeypatch.delenv("NETPULSE_DATABASE_URL", raising=False)

    result = main(["--output-dir", str(output_dir)])
    captured = capsys.readouterr()

    assert result == 1
    assert not output_dir.exists()
    assert "ValueError" in captured.err
    assert "NETPULSE_DATABASE_URL" not in captured.err


def test_database_failure_returns_nonzero_preserves_prior_export_and_redacts_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    marker = output_dir / "valid.csv"
    marker.write_bytes(b"previous\n")
    secret = "sentinel-password"
    monkeypatch.setenv("NETPULSE_DATABASE_URL", f"postgresql://reader:{secret}@localhost/netpulse")

    def fail(_config: TableauExportConfig) -> ExportSummary:
        raise psycopg.OperationalError(f"could not connect using {secret}")

    monkeypatch.setattr(cli, "export_tableau", fail)

    result = main(["--output-dir", str(output_dir)])
    captured = capsys.readouterr()

    assert result == 1
    assert marker.read_bytes() == b"previous\n"
    assert "OperationalError" in captured.err
    assert secret not in captured.out + captured.err


def test_filesystem_failure_returns_nonzero_and_preserves_prior_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "tableau_exports"
    output_dir.mkdir()
    marker = output_dir / "valid.csv"
    marker.write_bytes(b"previous\n")
    monkeypatch.setenv("NETPULSE_DATABASE_URL", "postgresql://reader@localhost/netpulse")

    def fail(_config: TableauExportConfig) -> ExportSummary:
        raise OSError("disk unavailable")

    monkeypatch.setattr(cli, "export_tableau", fail)

    result = main(["--output-dir", str(output_dir)])
    captured = capsys.readouterr()

    assert result == 1
    assert marker.read_bytes() == b"previous\n"
    assert "OSError" in captured.err
    assert "disk unavailable" not in captured.err
