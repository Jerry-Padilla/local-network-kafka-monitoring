"""Bounded HTTP/HTTPS service checker."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.config import EndpointConfig, HttpCollectorConfig, PrivacyConfig


@dataclass(frozen=True, slots=True)
class HttpResult:
    status: int
    time_to_first_byte_ms: float
    total_duration_ms: float


HttpProbe = Callable[[EndpointConfig, float, int], HttpResult]


def probe_http(
    endpoint: EndpointConfig,
    timeout_seconds: float,
    maximum_body_bytes: int,
) -> HttpResult:
    """Request a small response prefix and record supported timings."""
    request = urllib.request.Request(
        endpoint.address,
        headers={"User-Agent": "NetPulse-Agent/0.2"},
        method="GET",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        opened = time.monotonic()
        response.read(maximum_body_bytes)
        completed = time.monotonic()
        return HttpResult(
            status=response.status,
            time_to_first_byte_ms=(opened - started) * 1_000,
            total_duration_ms=(completed - started) * 1_000,
        )


class HttpCollector:
    """Check only explicitly configured HTTP(S) endpoints."""

    name = "http"

    def __init__(
        self,
        config: HttpCollectorConfig,
        privacy: PrivacyConfig,
        probe: HttpProbe = probe_http,
    ) -> None:
        self.interval_seconds = config.interval_seconds
        self._config = config
        self._privacy = privacy
        self._probe = probe

    def collect(self) -> list[CollectedEvent]:
        events: list[CollectedEvent] = []
        for endpoint in self._config.endpoints:
            fields: dict[str, object] = {
                "check_type": "http",
                "endpoint_id": endpoint.endpoint_id,
                "success": False,
                "dns_duration_ms": None,
                "tcp_duration_ms": None,
                "tls_duration_ms": None,
                "ttfb_ms": None,
                "total_duration_ms": None,
                "http_status": None,
                "timeout": False,
                "error_class": None,
            }
            if self._privacy.include_target_addresses:
                fields["url"] = endpoint.address
            try:
                result = self._probe(
                    endpoint,
                    self._config.timeout_seconds,
                    self._config.maximum_body_bytes,
                )
                fields["success"] = 200 <= result.status < 400
                fields["ttfb_ms"] = result.time_to_first_byte_ms
                fields["total_duration_ms"] = result.total_duration_ms
                fields["http_status"] = result.status
                if not fields["success"]:
                    fields["error_class"] = "HttpStatusError"
            except TimeoutError:
                fields["timeout"] = True
                fields["error_class"] = "Timeout"
            except urllib.error.HTTPError as error:
                fields["http_status"] = error.code
                fields["error_class"] = "HttpStatusError"
            except (urllib.error.URLError, OSError) as error:
                fields["error_class"] = type(error).__name__
            events.append(CollectedEvent("network.service_check", fields))
        return events
