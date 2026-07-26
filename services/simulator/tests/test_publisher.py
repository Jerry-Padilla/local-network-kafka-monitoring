from dataclasses import dataclass

from netpulse_simulator.config import SimulatorConfig
from netpulse_simulator.publisher import KafkaPublisher
from netpulse_simulator.scenarios import SimulatedRecord


@dataclass
class FakeMessage:
    def topic(self) -> str:
        return "test"

    def partition(self) -> int:
        return 0

    def offset(self) -> int:
        return 1


class FakeProducer:
    def __init__(self, _config: dict[str, object]) -> None:
        self.config = _config

    def produce(self, **kwargs) -> None:
        kwargs["on_delivery"](None, FakeMessage())

    def poll(self, _timeout: float) -> int:
        return 0

    def flush(self, _timeout: float) -> int:
        return 0


def test_delivery_callback_counts_acknowledgements(monkeypatch) -> None:
    monkeypatch.setattr("netpulse_simulator.publisher.Producer", FakeProducer)
    publisher = KafkaPublisher(SimulatorConfig())
    record = SimulatedRecord(topic="test", key="agent", value=b"{}")

    result = publisher.publish_batch([record])

    assert result.attempted == 1
    assert result.acknowledged == 1
    assert result.failed == 0
