from __future__ import annotations

import socket
from urllib.request import urlopen

import pytest
from netpulse_observability import MetricsHttpConfig, MetricsServer
from prometheus_client import CollectorRegistry, Gauge


def _unused_tcp_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def test_metrics_are_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NETPULSE_METRICS_ENABLED", raising=False)
    monkeypatch.delenv("NETPULSE_METRICS_HOST", raising=False)
    monkeypatch.delenv("NETPULSE_METRICS_PORT", raising=False)

    config = MetricsHttpConfig.from_env(default_port=9101)

    assert config == MetricsHttpConfig(enabled=False, host="127.0.0.1", port=9101)


@pytest.mark.parametrize("value", ["", "enabled", "2"])
def test_metrics_enabled_rejects_non_boolean_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("NETPULSE_METRICS_ENABLED", value)

    with pytest.raises(ValueError, match="NETPULSE_METRICS_ENABLED"):
        MetricsHttpConfig.from_env(default_port=9101)


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port"])
def test_metrics_port_rejects_values_outside_tcp_range(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("NETPULSE_METRICS_PORT", value)

    with pytest.raises(ValueError, match="NETPULSE_METRICS_PORT"):
        MetricsHttpConfig.from_env(default_port=9101)


def test_server_exposes_the_supplied_registry_and_has_idempotent_lifecycle() -> None:
    port = _unused_tcp_port()
    registry = CollectorRegistry()
    gauge = Gauge("netpulse_test_ready", "Test readiness.", registry=registry)
    gauge.set(1)
    server = MetricsServer(
        MetricsHttpConfig(enabled=True, host="127.0.0.1", port=port),
        registry,
    )

    server.start()
    server.start()
    try:
        with urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as response:
            body = response.read().decode("utf-8")
    finally:
        server.stop()
        server.stop()

    assert response.status == 200
    assert "netpulse_test_ready 1.0" in body


def test_disabled_server_does_not_bind_its_configured_port() -> None:
    port = _unused_tcp_port()
    server = MetricsServer(
        MetricsHttpConfig(enabled=False, host="127.0.0.1", port=port),
        CollectorRegistry(),
    )

    server.start()
    server.stop()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_server_rejects_an_invalid_bind_address() -> None:
    server = MetricsServer(
        MetricsHttpConfig(enabled=True, host="not-a-bind-address.invalid", port=9101),
        CollectorRegistry(),
    )

    with pytest.raises(OSError):
        server.start()


def test_server_reports_an_occupied_port() -> None:
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = int(occupied.getsockname()[1])
        server = MetricsServer(
            MetricsHttpConfig(enabled=True, host="127.0.0.1", port=port),
            CollectorRegistry(),
        )

        with pytest.raises(OSError):
            server.start()
