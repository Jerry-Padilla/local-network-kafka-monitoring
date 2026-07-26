from __future__ import annotations

import pytest
from netpulse_streaming.config import StreamingConfig


def test_environment_configuration_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
    monkeypatch.setenv("NETPULSE_STREAM_STARTING_OFFSETS", "latest")
    monkeypatch.setenv("NETPULSE_STREAM_FAIL_ON_DATA_LOSS", "false")
    monkeypatch.setenv("NETPULSE_STREAM_TRIGGER_MODE", "available-now")
    monkeypatch.setenv("NETPULSE_STREAM_SHUFFLE_PARTITIONS", "3")

    config = StreamingConfig.from_env()

    assert config.bootstrap_servers == "broker:9092"
    assert config.starting_offsets == "latest"
    assert config.fail_on_data_loss is False
    assert config.trigger_mode == "available-now"
    assert config.shuffle_partitions == 3


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NETPULSE_STREAM_STARTING_OFFSETS", "middle"),
        ("NETPULSE_STREAM_FAIL_ON_DATA_LOSS", "sometimes"),
        ("NETPULSE_STREAM_TRIGGER_MODE", "continuous"),
        ("NETPULSE_STREAM_CHECKPOINT_ROOT", "relative/checkpoint"),
        ("NETPULSE_STREAM_SHUFFLE_PARTITIONS", "0"),
        ("NETPULSE_STREAM_MAXIMUM_OUTPUT_ROWS", "0"),
    ],
)
def test_invalid_environment_configuration_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        StreamingConfig.from_env()
