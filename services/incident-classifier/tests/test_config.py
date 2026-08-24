from __future__ import annotations

import pytest
from netpulse_classifier.config import ClassifierConfig


def test_environment_overrides_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETPULSE_CLASSIFIER_LOOKBACK_SECONDS", "90")
    monkeypatch.setenv("NETPULSE_CLASSIFIER_MINIMUM_SAMPLES", "3")
    monkeypatch.setenv("NETPULSE_CLASSIFIER_HIGH_LATENCY_MS", "175")

    value = ClassifierConfig.from_env()

    assert value.lookback_seconds == 90
    assert value.minimum_samples == 3
    assert value.high_latency_ms == 175


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NETPULSE_CLASSIFIER_LOOKBACK_SECONDS", "0"),
        ("NETPULSE_CLASSIFIER_MINIMUM_SAMPLES", "0"),
        ("NETPULSE_CLASSIFIER_INTERVAL_SECONDS", "0"),
        ("NETPULSE_CLASSIFIER_FAILED_SUCCESS_PCT", "90"),
        ("NETPULSE_CLASSIFIER_HEALTHY_SUCCESS_PCT", "10"),
        ("NETPULSE_CLASSIFIER_HIGH_PACKET_LOSS_PCT", "101"),
        ("NETPULSE_CLASSIFIER_WEAK_SIGNAL_DBM", "-121"),
    ],
)
def test_invalid_configuration_is_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        ClassifierConfig.from_env()
