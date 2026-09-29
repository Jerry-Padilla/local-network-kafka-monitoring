from __future__ import annotations

from typing import ClassVar

import pytest
from netpulse_ingestion import cli
from netpulse_ingestion.config import IngestionConfig


class FakeRepository:
    instances: ClassVar[list[FakeRepository]] = []

    def __init__(self, _url: str) -> None:
        self.calls: list[str] = []
        type(self).instances.append(self)

    def open(self) -> None:
        self.calls.append("open")

    def close(self) -> None:
        self.calls.append("close")

    def healthcheck(self) -> bool:
        self.calls.append("healthcheck")
        return True

    def load_reference_ids(self) -> tuple[set[str], set[str]]:
        self.calls.append("load_references")
        return {"network-agent-wifi-01"}, {"public-dns-a"}


class FakePublisher:
    def __init__(self, **_kwargs) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeConsumer:
    def __init__(self, _config, _processor, _metrics) -> None:
        self.calls: list[str] = []

    def install_signal_handlers(self) -> None:
        self.calls.append("signals")

    def run(self) -> None:
        self.calls.append("run")


def config() -> IngestionConfig:
    return IngestionConfig(
        bootstrap_servers="broker:9092",
        database_url="postgresql://example",
        consumer_group="group",
        client_id="client",
        max_processing_attempts=2,
        retry_base_seconds=0.1,
        delivery_timeout_seconds=1,
    )


def configure_fakes(monkeypatch) -> None:
    monkeypatch.setattr(cli, "configure_logging", lambda _service: None)
    monkeypatch.setattr(cli.IngestionConfig, "from_env", classmethod(lambda cls: config()))
    monkeypatch.setattr(cli, "PostgresEventRepository", FakeRepository)


class FakeMetricsServer:
    instances: ClassVar[list[FakeMetricsServer]] = []

    def __init__(self, _config, _registry) -> None:
        self.calls: list[str] = []
        type(self).instances.append(self)

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")


def test_healthcheck_command_opens_and_closes_repository(monkeypatch) -> None:
    configure_fakes(monkeypatch)
    monkeypatch.setattr(cli, "MetricsServer", FakeMetricsServer)
    before = len(FakeMetricsServer.instances)

    assert cli.main(["healthcheck"]) == 0
    assert FakeRepository.instances[-1].calls == ["open", "healthcheck", "close"]
    assert len(FakeMetricsServer.instances) == before


def test_run_command_closes_publisher_and_repository(monkeypatch) -> None:
    configure_fakes(monkeypatch)
    monkeypatch.setattr(cli, "SynchronousKafkaPublisher", FakePublisher)
    monkeypatch.setattr(cli, "IngestionConsumer", FakeConsumer)
    monkeypatch.setattr(cli, "MetricsServer", FakeMetricsServer)

    assert cli.main(["run"]) == 0
    assert FakeRepository.instances[-1].calls == ["open", "load_references", "close"]
    assert FakeMetricsServer.instances[-1].calls == ["start", "stop"]


def test_metrics_server_stops_when_publisher_initialization_fails(monkeypatch) -> None:
    configure_fakes(monkeypatch)
    monkeypatch.setattr(cli, "MetricsServer", FakeMetricsServer)

    class FailingPublisher:
        def __init__(self, **_kwargs) -> None:
            raise RuntimeError("publisher initialization failed")

    monkeypatch.setattr(cli, "SynchronousKafkaPublisher", FailingPublisher)

    with pytest.raises(RuntimeError, match="publisher initialization failed"):
        cli.main(["run"])

    assert FakeMetricsServer.instances[-1].calls == ["start", "stop"]
    assert FakeRepository.instances[-1].calls == ["open", "load_references", "close"]
