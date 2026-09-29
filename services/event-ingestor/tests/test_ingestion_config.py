import pytest
from netpulse_ingestion.config import IngestionConfig


def test_invalid_attempt_count_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("NETPULSE_MAX_PROCESSING_ATTEMPTS", "0")

    with pytest.raises(ValueError, match="at least 1"):
        IngestionConfig.from_env()


def test_metrics_default_to_disabled_on_ingestor_port(monkeypatch) -> None:
    monkeypatch.delenv("NETPULSE_METRICS_ENABLED", raising=False)
    monkeypatch.delenv("NETPULSE_METRICS_HOST", raising=False)
    monkeypatch.delenv("NETPULSE_METRICS_PORT", raising=False)

    config = IngestionConfig.from_env()

    assert config.metrics.enabled is False
    assert config.metrics.host == "127.0.0.1"
    assert config.metrics.port == 9101


def test_metrics_can_be_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setenv("NETPULSE_METRICS_ENABLED", "true")
    monkeypatch.setenv("NETPULSE_METRICS_HOST", "0.0.0.0")
    monkeypatch.setenv("NETPULSE_METRICS_PORT", "19101")

    config = IngestionConfig.from_env()

    assert config.metrics.enabled is True
    assert config.metrics.host == "0.0.0.0"
    assert config.metrics.port == 19101
