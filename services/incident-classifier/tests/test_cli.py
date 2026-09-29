from __future__ import annotations

from typing import ClassVar

from netpulse_classifier import cli


class FakeRepository:
    def __init__(self, _database_url: str) -> None:
        self.closed = False

    def open(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakePublisher:
    def __init__(self, *_args) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeService:
    evaluations = 0

    def __init__(self, *_args) -> None:
        return None

    def evaluate_once(self) -> int:
        type(self).evaluations += 1
        return 0


class OneCycleEvent:
    def __init__(self) -> None:
        self.checks = 0

    def is_set(self) -> bool:
        self.checks += 1
        return self.checks > 1

    def set(self) -> None:
        self.checks = 2

    def wait(self, _timeout: float) -> bool:
        return False


class FakeMetricsServer:
    instances: ClassVar[list[FakeMetricsServer]] = []

    def __init__(self, _config, _registry) -> None:
        self.calls: list[str] = []
        type(self).instances.append(self)

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")


def test_run_starts_and_stops_metrics_server(monkeypatch) -> None:
    FakeService.evaluations = 0
    monkeypatch.setattr(cli, "configure_logging", lambda _name: None)
    monkeypatch.setattr(cli, "PostgresIncidentRepository", FakeRepository)
    monkeypatch.setattr(cli, "IncidentPublisher", FakePublisher)
    monkeypatch.setattr(cli, "IncidentClassifierService", FakeService)
    monkeypatch.setattr(cli, "MetricsServer", FakeMetricsServer)
    monkeypatch.setattr(cli, "Event", OneCycleEvent)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args: None)

    assert cli.main(["run"]) == 0
    assert FakeService.evaluations == 1
    assert FakeMetricsServer.instances[-1].calls == ["start", "stop"]
