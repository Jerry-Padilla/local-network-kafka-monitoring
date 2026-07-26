from __future__ import annotations

import dns.exception
from netpulse_agent.collectors.dns import DnsCollector, DnsResult
from netpulse_agent.collectors.http import HttpCollector, HttpResult
from netpulse_agent.config import (
    DnsCollectorConfig,
    DnsEndpointConfig,
    EndpointConfig,
    HttpCollectorConfig,
    PrivacyConfig,
)


def test_dns_success_uses_aliases_under_default_privacy() -> None:
    config = DnsCollectorConfig(
        endpoints=[
            DnsEndpointConfig(
                endpoint_id="dns-a",
                domain="example.test",
                resolver="192.0.2.53",
            )
        ]
    )
    event = DnsCollector(
        config,
        PrivacyConfig(),
        query=lambda _endpoint, _timeout: DnsResult(2, 4.5),
    ).collect()[0]

    assert event.fields["success"] is True
    assert event.fields["resolver"] == "dns-a"
    assert event.fields["domain"] == "dns-a"
    assert event.fields["returned_record_count"] == 2


def test_dns_timeout_is_reported() -> None:
    config = DnsCollectorConfig(
        endpoints=[
            DnsEndpointConfig(
                endpoint_id="dns-a",
                domain="example.test",
                resolver="192.0.2.53",
            )
        ]
    )

    def timeout(_endpoint: DnsEndpointConfig, _seconds: float) -> DnsResult:
        raise dns.exception.Timeout

    event = DnsCollector(config, PrivacyConfig(), query=timeout).collect()[0]
    assert event.fields["success"] is False
    assert event.fields["timeout"] is True
    assert event.fields["error_class"] == "Timeout"


def test_http_success_records_bounded_supported_timings() -> None:
    config = HttpCollectorConfig(
        endpoints=[
            EndpointConfig(
                endpoint_id="service-a",
                address="https://service.example.test/health",
            )
        ]
    )
    event = HttpCollector(
        config,
        PrivacyConfig(),
        probe=lambda _endpoint, _timeout, _maximum: HttpResult(204, 5.0, 8.0),
    ).collect()[0]

    assert event.fields["success"] is True
    assert event.fields["http_status"] == 204
    assert event.fields["ttfb_ms"] == 5.0
    assert event.fields["total_duration_ms"] == 8.0
    assert "url" not in event.fields
