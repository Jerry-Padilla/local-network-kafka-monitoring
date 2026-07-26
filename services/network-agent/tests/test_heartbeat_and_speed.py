from __future__ import annotations

import json

from netpulse_agent.collectors.heartbeat import HeartbeatCollector, SystemSnapshot
from netpulse_agent.collectors.speed_test import SpeedTestCollector
from netpulse_agent.commands import CommandResult
from netpulse_agent.config import SpeedTestCollectorConfig


def test_heartbeat_includes_queue_depth_and_collection_errors() -> None:
    snapshot = SystemSnapshot(
        hostname="agent",
        device_model="Raspberry Pi",
        os_version="Linux",
        uptime_seconds=10,
        cpu_temperature_c=42,
        cpu_utilization_pct=5,
        memory_utilization_pct=25,
        disk_utilization_pct=30,
        network_interfaces=["eth0"],
    )
    event = HeartbeatCollector(
        60,
        "0.2.0",
        queue_depth=lambda: 7,
        collection_errors=lambda: ["wifi: FileNotFoundError"],
        probe=lambda: snapshot,
    ).collect()[0]

    assert event.fields["local_queue_depth"] == 7
    assert event.fields["collection_errors"] == ["wifi: FileNotFoundError"]


def test_speed_test_converts_bits_per_second_and_bytes() -> None:
    payload = {
        "download": 125_000_000,
        "upload": 25_000_000,
        "ping": 15.5,
        "bytes_received": 100,
        "bytes_sent": 25,
        "server": {"id": "42"},
    }
    collector = SpeedTestCollector(
        SpeedTestCollectorConfig(enabled=True),
        runner=lambda _arguments, _timeout: CommandResult(0, json.dumps(payload), ""),
    )

    event = collector.collect()[0]

    assert event.fields["success"] is True
    assert event.fields["download_mbps"] == 125.0
    assert event.fields["upload_mbps"] == 25.0
    assert event.fields["bytes_transferred"] == 125
    assert event.fields["server_id"] == "42"
