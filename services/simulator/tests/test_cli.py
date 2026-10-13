from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime

import pytest
from netpulse_simulator import cli
from netpulse_simulator.config import SimulatorConfig


def test_dry_run_scenario_emits_one_deterministic_round(monkeypatch, capsys) -> None:
    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    args = Namespace(
        duration=1,
        rate=1.0,
        seed=4,
        dry_run=True,
        scenario="healthy",
        start_time=datetime(2035, 1, 15, 12, tzinfo=UTC),
    )

    assert cli._run_scenario(args, SimulatorConfig()) == 0
    output = capsys.readouterr().out
    assert '"event_type": "network.measurement"' in output
    assert '"event_time": "2035-01-15T12:00:00Z"' in output


def test_start_time_requires_timezone_aware_utc() -> None:
    parser = cli._parser()

    parsed = parser.parse_args(["run", "--start-time", "2035-01-15T12:00:00Z", "--dry-run"])
    assert parsed.start_time == datetime(2035, 1, 15, 12, tzinfo=UTC)

    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--start-time", "2035-01-15T12:00:00", "--dry-run"])


def test_dry_run_load_test_emits_requested_batch(monkeypatch, capsys) -> None:
    ticks = iter([0.0, 0.0, 0.5])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    args = Namespace(duration=1, rate=2, seed=4, dry_run=True)

    assert cli._run_load_test(args, SimulatorConfig()) == 0
    assert capsys.readouterr().out.count('"event_id"') == 2


def test_main_routes_to_scenario_runner(monkeypatch) -> None:
    monkeypatch.setattr(cli, "configure_logging", lambda _service: None)
    monkeypatch.setattr(
        cli,
        "_run_scenario",
        lambda args, config: 17,
    )

    assert cli.main(["run", "--duration", "1", "--dry-run"]) == 17
