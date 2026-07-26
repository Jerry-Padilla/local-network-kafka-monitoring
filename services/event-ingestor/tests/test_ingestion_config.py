import pytest
from netpulse_ingestion.config import IngestionConfig


def test_invalid_attempt_count_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("NETPULSE_MAX_PROCESSING_ATTEMPTS", "0")

    with pytest.raises(ValueError, match="at least 1"):
        IngestionConfig.from_env()
