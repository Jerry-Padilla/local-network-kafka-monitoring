from __future__ import annotations

from netpulse_agent.collectors.wifi import WifiCollector
from netpulse_agent.commands import CommandResult
from netpulse_agent.config import PrivacyConfig, WifiCollectorConfig

IW_OUTPUT = """
Connected to AA:BB:CC:DD:EE:FF (on wlan0)
\tSSID: Example Home
\tfreq: 2437
\tsignal: -54 dBm
\ttx bitrate: 43.3 MBit/s
"""


def test_wifi_output_is_parsed_and_hashed() -> None:
    event = WifiCollector(
        WifiCollectorConfig(interface="wlan0"),
        PrivacyConfig(ssid="hash", bssid="hash", hash_salt="12345678"),
        runner=lambda _arguments, _timeout: CommandResult(0, IW_OUTPUT, ""),
    ).collect()[0]

    assert event.fields["connected"] is True
    assert event.fields["signal_dbm"] == -54.0
    assert event.fields["frequency_mhz"] == 2_437
    assert event.fields["bitrate_mbps"] == 43.3
    assert str(event.fields["ssid"]).startswith("sha256:")
    assert str(event.fields["bssid"]).startswith("sha256:")


def test_missing_iw_returns_failure_instead_of_crashing() -> None:
    def unavailable(_arguments: list[str], _timeout: float) -> CommandResult:
        raise FileNotFoundError("iw")

    event = WifiCollector(
        WifiCollectorConfig(),
        PrivacyConfig(),
        runner=unavailable,
    ).collect()[0]

    assert event.fields["connected"] is False
    assert event.fields["success"] is False
    assert event.fields["error_class"] == "FileNotFoundError"
