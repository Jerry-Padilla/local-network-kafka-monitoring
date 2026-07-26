"""Linux ping collector and parser."""

from __future__ import annotations

import math
import re
import subprocess
from typing import Literal

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.commands import CommandRunner, run_command
from netpulse_agent.config import PingCollectorConfig, PrivacyConfig

_PACKET_LOSS = re.compile(r"(\d+(?:\.\d+)?)%\s+packet loss")
_ROUND_TRIP = re.compile(
    r"(?:rtt|round-trip).*?=\s*"
    r"(?P<minimum>\d+(?:\.\d+)?)/(?P<average>\d+(?:\.\d+)?)/"
    r"(?P<maximum>\d+(?:\.\d+)?)/(?P<jitter>\d+(?:\.\d+)?)"
)


class PingCollector:
    """Collect router or external reachability without invoking a shell."""

    def __init__(
        self,
        name: str,
        measurement_type: Literal["router_ping", "external_ping"],
        config: PingCollectorConfig,
        privacy: PrivacyConfig,
        runner: CommandRunner = run_command,
    ) -> None:
        self.name = name
        self.interval_seconds = config.interval_seconds
        self._measurement_type = measurement_type
        self._config = config
        self._privacy = privacy
        self._runner = runner

    def collect(self) -> list[CollectedEvent]:
        events: list[CollectedEvent] = []
        for endpoint in self._config.endpoints:
            fields: dict[str, object] = {
                "measurement_type": self._measurement_type,
                "target_id": endpoint.endpoint_id,
                "success": False,
                "latency_ms": None,
                "packet_loss_pct": 100.0,
                "jitter_ms": None,
                "error_class": None,
                "error_message": None,
            }
            if self._privacy.include_target_addresses:
                fields["target_address"] = endpoint.address
            command = [
                "ping",
                "-n",
                "-c",
                str(self._config.sample_count),
                "-W",
                str(math.ceil(self._config.timeout_seconds)),
                endpoint.address,
            ]
            try:
                result = self._runner(command, self._config.timeout_seconds + 2)
                combined = f"{result.stdout}\n{result.stderr}"
                loss_match = _PACKET_LOSS.search(combined)
                loss = float(loss_match.group(1)) if loss_match else 100.0
                timing_match = _ROUND_TRIP.search(combined)
                success = result.return_code == 0 and loss < 100 and timing_match is not None
                fields["success"] = success
                fields["packet_loss_pct"] = loss
                if success and timing_match is not None:
                    fields["latency_ms"] = float(timing_match.group("average"))
                    fields["jitter_ms"] = float(timing_match.group("jitter"))
                else:
                    fields["error_class"] = "PingFailed"
                    fields["error_message"] = (result.stderr or result.stdout).strip()[:1024]
            except subprocess.TimeoutExpired:
                fields["error_class"] = "Timeout"
                fields["error_message"] = "ping command exceeded its timeout"
            except (FileNotFoundError, OSError) as error:
                fields["error_class"] = type(error).__name__
                fields["error_message"] = str(error)[:1024]
            events.append(CollectedEvent("network.measurement", fields))
        return events
