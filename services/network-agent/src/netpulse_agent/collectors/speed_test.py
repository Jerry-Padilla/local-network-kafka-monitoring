"""Optional non-overlapping speed-test collector."""

from __future__ import annotations

import json
import subprocess
import threading
import time

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.commands import CommandRunner, run_command
from netpulse_agent.config import SpeedTestCollectorConfig


class SpeedTestCollector:
    """Run speedtest-cli at a low configured frequency."""

    name = "speed_test"

    def __init__(
        self,
        config: SpeedTestCollectorConfig,
        runner: CommandRunner = run_command,
    ) -> None:
        self.interval_seconds = config.interval_seconds
        self._config = config
        self._runner = runner
        self._lock = threading.Lock()

    def collect(self) -> list[CollectedEvent]:
        if not self._lock.acquire(blocking=False):
            return []
        started = time.monotonic()
        fields: dict[str, object] = {
            "provider": self._config.provider,
            "server_id": self._config.server_id,
            "success": False,
            "download_mbps": None,
            "upload_mbps": None,
            "latency_ms": None,
            "duration_ms": 0.0,
            "bytes_transferred": 0,
            "error_class": None,
        }
        try:
            command = ["speedtest-cli", "--json", "--secure"]
            if self._config.server_id is not None:
                command.extend(["--server", self._config.server_id])
            result = self._runner(command, self._config.timeout_seconds)
            fields["duration_ms"] = (time.monotonic() - started) * 1_000
            if result.return_code != 0:
                fields["error_class"] = "SpeedTestFailed"
            else:
                payload = json.loads(result.stdout)
                fields.update(
                    {
                        "success": True,
                        "download_mbps": float(payload["download"]) / 1_000_000,
                        "upload_mbps": float(payload["upload"]) / 1_000_000,
                        "latency_ms": float(payload["ping"]),
                        "bytes_transferred": int(payload.get("bytes_received", 0))
                        + int(payload.get("bytes_sent", 0)),
                        "server_id": str(payload.get("server", {}).get("id"))
                        if payload.get("server")
                        else self._config.server_id,
                    }
                )
        except subprocess.TimeoutExpired:
            fields["duration_ms"] = (time.monotonic() - started) * 1_000
            fields["error_class"] = "Timeout"
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            fields["duration_ms"] = (time.monotonic() - started) * 1_000
            fields["error_class"] = "SpeedTestUnavailable"
        finally:
            self._lock.release()
        return [CollectedEvent("network.speed_test", fields)]
