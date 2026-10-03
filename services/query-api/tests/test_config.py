"""Environment-backed query API configuration contract."""

from dataclasses import FrozenInstanceError

import pytest
from netpulse_query_api.config import QueryApiConfig


def test_config_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in (None, "", "  \t "):
        if value is None:
            monkeypatch.delenv("NETPULSE_DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("NETPULSE_DATABASE_URL", value)
        with pytest.raises(ValueError, match="NETPULSE_DATABASE_URL"):
            QueryApiConfig.from_env()


def test_config_loads_bounded_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETPULSE_DATABASE_URL", " postgresql://local@localhost/netpulse ")
    for name in (
        "NETPULSE_QUERY_API_POOL_MIN_SIZE",
        "NETPULSE_QUERY_API_POOL_MAX_SIZE",
        "NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS",
        "NETPULSE_QUERY_API_STATEMENT_TIMEOUT_MS",
        "NETPULSE_QUERY_API_LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)

    config = QueryApiConfig.from_env()

    assert config.database_url == "postgresql://local@localhost/netpulse"
    assert config.pool_min_size == 1
    assert config.pool_max_size == 5
    assert config.pool_acquire_timeout_seconds == 2.0
    assert config.statement_timeout_ms == 3000
    assert config.log_level == "INFO"
    with pytest.raises(FrozenInstanceError):
        config.pool_max_size = 10  # type: ignore[misc]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NETPULSE_QUERY_API_POOL_MIN_SIZE", "0"),
        ("NETPULSE_QUERY_API_POOL_MAX_SIZE", "0"),
        ("NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS", "0"),
        ("NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS", "-1"),
        ("NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS", "nan"),
        ("NETPULSE_QUERY_API_STATEMENT_TIMEOUT_MS", "0"),
        ("NETPULSE_QUERY_API_STATEMENT_TIMEOUT_MS", "-1"),
    ],
)
def test_config_rejects_invalid_pool_and_timeouts(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("NETPULSE_DATABASE_URL", "postgresql://local@localhost/netpulse")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        QueryApiConfig.from_env()


def test_config_rejects_maximum_below_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETPULSE_DATABASE_URL", "postgresql://local@localhost/netpulse")
    monkeypatch.setenv("NETPULSE_QUERY_API_POOL_MIN_SIZE", "4")
    monkeypatch.setenv("NETPULSE_QUERY_API_POOL_MAX_SIZE", "3")

    with pytest.raises(ValueError):
        QueryApiConfig.from_env()


def test_config_loads_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETPULSE_DATABASE_URL", "postgresql://local@localhost/netpulse")
    monkeypatch.setenv("NETPULSE_QUERY_API_POOL_MIN_SIZE", "2")
    monkeypatch.setenv("NETPULSE_QUERY_API_POOL_MAX_SIZE", "4")
    monkeypatch.setenv("NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("NETPULSE_QUERY_API_STATEMENT_TIMEOUT_MS", "2500")
    monkeypatch.setenv("NETPULSE_QUERY_API_LOG_LEVEL", "DEBUG")

    config = QueryApiConfig.from_env()

    assert (config.pool_min_size, config.pool_max_size) == (2, 4)
    assert config.pool_acquire_timeout_seconds == 1.5
    assert config.statement_timeout_ms == 2500
    assert config.log_level == "DEBUG"
