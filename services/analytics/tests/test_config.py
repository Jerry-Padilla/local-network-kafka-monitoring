import pytest
from netpulse_analytics.config import AnalyticsConfig


def test_database_url_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql://local@localhost/netpulse"
    monkeypatch.setenv("NETPULSE_DATABASE_URL", database_url)

    assert AnalyticsConfig.from_env().database_url == database_url


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NETPULSE_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="NETPULSE_DATABASE_URL"):
        AnalyticsConfig.from_env()
