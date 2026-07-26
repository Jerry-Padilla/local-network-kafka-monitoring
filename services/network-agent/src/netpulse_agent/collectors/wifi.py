"""Raspberry Pi OS Wi-Fi link diagnostics."""

from __future__ import annotations

import re
import subprocess

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.commands import CommandRunner, run_command
from netpulse_agent.config import PrivacyConfig, WifiCollectorConfig
from netpulse_agent.privacy import protect_wifi_identifiers

_BSSID = re.compile(r"Connected to\s+([0-9a-fA-F:]{17})")
_SSID = re.compile(r"^\s*SSID:\s*(.+)$", re.MULTILINE)
_FREQUENCY = re.compile(r"^\s*freq:\s*(\d+)", re.MULTILINE)
_SIGNAL = re.compile(r"^\s*signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", re.MULTILINE)
_BITRATE = re.compile(r"^\s*tx bitrate:\s*(\d+(?:\.\d+)?)\s*MBit/s", re.MULTILINE)


class WifiCollector:
    """Collect `iw` link output; missing Wi-Fi is a normal event, not a crash."""

    name = "wifi"

    def __init__(
        self,
        config: WifiCollectorConfig,
        privacy: PrivacyConfig,
        runner: CommandRunner = run_command,
    ) -> None:
        self.interval_seconds = config.interval_seconds
        self._config = config
        self._privacy = privacy
        self._runner = runner

    def collect(self) -> list[CollectedEvent]:
        fields: dict[str, object] = {
            "measurement_type": "wifi_diagnostics",
            "target_id": self._config.endpoint_id,
            "success": False,
            "latency_ms": None,
            "packet_loss_pct": 100.0,
            "jitter_ms": None,
            "signal_dbm": None,
            "connected": False,
            "error_class": None,
            "error_message": None,
            "interface_name": self._config.interface,
        }
        try:
            result = self._runner(["iw", "dev", self._config.interface, "link"], 5)
            output = result.stdout
            connected = result.return_code == 0 and "Not connected" not in output
            fields["connected"] = connected
            fields["success"] = connected
            fields["packet_loss_pct"] = 0.0 if connected else 100.0
            if connected:
                ssid_match = _SSID.search(output)
                bssid_match = _BSSID.search(output)
                safe_ssid, safe_bssid = protect_wifi_identifiers(
                    ssid_match.group(1).strip() if ssid_match else None,
                    bssid_match.group(1).lower() if bssid_match else None,
                    self._privacy,
                )
                signal_match = _SIGNAL.search(output)
                frequency_match = _FREQUENCY.search(output)
                bitrate_match = _BITRATE.search(output)
                fields.update(
                    {
                        "ssid": safe_ssid,
                        "bssid": safe_bssid,
                        "signal_dbm": float(signal_match.group(1)) if signal_match else None,
                        "frequency_mhz": (
                            int(frequency_match.group(1)) if frequency_match else None
                        ),
                        "bitrate_mbps": (float(bitrate_match.group(1)) if bitrate_match else None),
                    }
                )
            else:
                fields["error_class"] = "WifiDisconnected"
                fields["error_message"] = (result.stderr or output).strip()[:1024]
        except subprocess.TimeoutExpired:
            fields["error_class"] = "Timeout"
            fields["error_message"] = "iw command exceeded its timeout"
        except (FileNotFoundError, OSError) as error:
            fields["error_class"] = type(error).__name__
            fields["error_message"] = str(error)[:1024]
        return [CollectedEvent("network.measurement", fields)]
