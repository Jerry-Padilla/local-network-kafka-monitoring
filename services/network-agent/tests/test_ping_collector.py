from __future__ import annotations

import subprocess

from netpulse_agent.collectors.ping import PingCollector
from netpulse_agent.commands import CommandResult
from netpulse_agent.config import EndpointConfig, PingCollectorConfig, PrivacyConfig


def _config() -> PingCollectorConfig:
    return PingCollectorConfig(
        endpoints=[EndpointConfig(endpoint_id="router", address="192.0.2.1")]
    )


def test_successful_ping_is_parsed_without_exposing_address() -> None:
    output = """
3 packets transmitted, 3 received, 0% packet loss, time 2002ms
rtt min/avg/max/mdev = 10.000/12.500/14.000/1.250 ms
"""
    collector = PingCollector(
        "router_ping",
        "router_ping",
        _config(),
        PrivacyConfig(),
        runner=lambda _arguments, _timeout: CommandResult(0, output, ""),
    )

    event = collector.collect()[0]

    assert event.fields["success"] is True
    assert event.fields["latency_ms"] == 12.5
    assert event.fields["jitter_ms"] == 1.25
    assert "target_address" not in event.fields


def test_ping_timeout_is_a_valid_failure_event() -> None:
    def timeout(_arguments: list[str], _seconds: float) -> CommandResult:
        raise subprocess.TimeoutExpired("ping", 2)

    event = PingCollector(
        "external_ping",
        "external_ping",
        _config(),
        PrivacyConfig(include_target_addresses=True),
        runner=timeout,
    ).collect()[0]

    assert event.fields["success"] is False
    assert event.fields["latency_ms"] is None
    assert event.fields["error_class"] == "Timeout"
    assert event.fields["target_address"] == "192.0.2.1"
