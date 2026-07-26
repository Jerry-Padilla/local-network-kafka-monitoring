from __future__ import annotations

from typing import ClassVar

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


class FakePublisher:
    def __init__(self, **_kwargs) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeConsumer:
    def __init__(self, _config, _processor) -> None:
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


def test_healthcheck_command_opens_and_closes_repository(monkeypatch) -> None:
    configure_fakes(monkeypatch)

    assert cli.main(["healthcheck"]) == 0
    assert FakeRepository.instances[-1].calls == ["open", "healthcheck", "close"]


def test_run_command_closes_publisher_and_repository(monkeypatch) -> None:
    configure_fakes(monkeypatch)
    monkeypatch.setattr(cli, "SynchronousKafkaPublisher", FakePublisher)
    monkeypatch.setattr(cli, "IngestionConsumer", FakeConsumer)

    assert cli.main(["run"]) == 0
    assert FakeRepository.instances[-1].calls == ["open", "close"]
