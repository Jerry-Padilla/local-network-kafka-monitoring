from __future__ import annotations

import pytest
from netpulse_classifier.publisher import IncidentPublicationError, IncidentPublisher


class FakeProducer:
    callback_error = None
    invoke_callback = True
    buffer_once = False

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.calls = 0

    def produce(self, *_args: object, **kwargs: object) -> None:
        self.calls += 1
        if self.buffer_once and self.calls == 1:
            raise BufferError
        if self.invoke_callback:
            callback = kwargs["on_delivery"]
            assert callable(callback)
            callback(self.callback_error, object())

    def poll(self, _timeout: float) -> int:
        return 0

    def flush(self, _timeout: float) -> int:
        return 0


def publisher(monkeypatch: pytest.MonkeyPatch) -> IncidentPublisher:
    monkeypatch.setattr("netpulse_classifier.publisher.Producer", FakeProducer)
    return IncidentPublisher("broker:9092", "classifier-test", 0.1)


def test_publisher_uses_idempotence_and_waits_for_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeProducer.callback_error = None
    FakeProducer.invoke_callback = True
    FakeProducer.buffer_once = True
    instance = publisher(monkeypatch)

    instance.publish("incidents", "incident-id", b"{}")
    instance.close()

    assert instance._producer.config["enable.idempotence"] is True
    assert instance._producer.config["acks"] == "all"


def test_delivery_error_is_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeProducer.callback_error = "broker rejected incident"
    FakeProducer.invoke_callback = True
    FakeProducer.buffer_once = False
    instance = publisher(monkeypatch)

    with pytest.raises(IncidentPublicationError, match="broker rejected"):
        instance.publish("incidents", "incident-id", b"{}")


def test_delivery_timeout_is_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeProducer.callback_error = None
    FakeProducer.invoke_callback = False
    ticks = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr("netpulse_classifier.publisher.time.monotonic", lambda: next(ticks))
    instance = publisher(monkeypatch)

    with pytest.raises(IncidentPublicationError, match="timed out"):
        instance.publish("incidents", "incident-id", b"{}")


def test_close_rejects_unflushed_records(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = publisher(monkeypatch)
    instance._producer.flush = lambda _timeout: 1

    with pytest.raises(IncidentPublicationError, match="remained"):
        instance.close()
