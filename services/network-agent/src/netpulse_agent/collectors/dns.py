"""Configurable DNS resolution collector."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import dns.exception
import dns.resolver

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.config import DnsCollectorConfig, DnsEndpointConfig, PrivacyConfig


@dataclass(frozen=True, slots=True)
class DnsResult:
    record_count: int
    duration_ms: float


DnsQuery = Callable[[DnsEndpointConfig, float], DnsResult]


def query_dns(endpoint: DnsEndpointConfig, timeout_seconds: float) -> DnsResult:
    """Query one explicit resolver without changing host resolver settings."""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [endpoint.resolver]
    resolver.timeout = timeout_seconds
    resolver.lifetime = timeout_seconds
    started = time.monotonic()
    answer = resolver.resolve(endpoint.domain, endpoint.record_type, search=False)
    duration_ms = (time.monotonic() - started) * 1_000
    return DnsResult(len(answer), duration_ms)


class DnsCollector:
    """Collect DNS success and lookup duration."""

    name = "dns"

    def __init__(
        self,
        config: DnsCollectorConfig,
        privacy: PrivacyConfig,
        query: DnsQuery = query_dns,
    ) -> None:
        self.interval_seconds = config.interval_seconds
        self._config = config
        self._privacy = privacy
        self._query = query

    def collect(self) -> list[CollectedEvent]:
        events: list[CollectedEvent] = []
        for endpoint in self._config.endpoints:
            fields: dict[str, object] = {
                "check_type": "dns",
                "endpoint_id": endpoint.endpoint_id,
                "success": False,
                "resolver": endpoint.resolver,
                "domain": endpoint.domain,
                "lookup_duration_ms": None,
                "returned_record_count": None,
                "timeout": False,
                "error_class": None,
            }
            if not self._privacy.include_target_addresses:
                fields["resolver"] = endpoint.endpoint_id
                fields["domain"] = endpoint.endpoint_id
            try:
                result = self._query(endpoint, self._config.timeout_seconds)
                fields["success"] = True
                fields["lookup_duration_ms"] = result.duration_ms
                fields["returned_record_count"] = result.record_count
            except dns.exception.Timeout:
                fields["timeout"] = True
                fields["error_class"] = "Timeout"
            except Exception as error:
                fields["error_class"] = type(error).__name__
            events.append(CollectedEvent("network.service_check", fields))
        return events
