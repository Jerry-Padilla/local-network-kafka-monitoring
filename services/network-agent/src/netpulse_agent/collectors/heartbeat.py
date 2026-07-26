"""Dependency-free Linux and Raspberry Pi health collection."""

from __future__ import annotations

import os
import platform
import shutil
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from netpulse_agent.collector_types import CollectedEvent


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except OSError:
        return None


def _percentage(used: float, total: float) -> float:
    return min(100.0, max(0.0, used / total * 100)) if total > 0 else 0.0


@dataclass(frozen=True, slots=True)
class SystemSnapshot:
    hostname: str
    device_model: str | None
    os_version: str
    uptime_seconds: float
    cpu_temperature_c: float | None
    cpu_utilization_pct: float
    memory_utilization_pct: float
    disk_utilization_pct: float
    network_interfaces: list[str]


SystemProbe = Callable[[], SystemSnapshot]


def collect_system_snapshot() -> SystemSnapshot:
    """Collect bounded system metadata using Linux procfs/sysfs where available."""
    uptime_text = _read_text(Path("/proc/uptime"))
    uptime = float(uptime_text.split()[0]) if uptime_text else 0.0

    temperature_text = _read_text(Path("/sys/class/thermal/thermal_zone0/temp"))
    temperature = float(temperature_text) / 1_000 if temperature_text else None

    load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    cpu_count = os.cpu_count() or 1
    cpu_percent = min(100.0, max(0.0, load / cpu_count * 100))

    memory_text = _read_text(Path("/proc/meminfo")) or ""
    memory: dict[str, float] = {}
    for line in memory_text.splitlines():
        key, _, raw_value = line.partition(":")
        if raw_value:
            memory[key] = float(raw_value.strip().split()[0])
    total_memory = memory.get("MemTotal", 0)
    available_memory = memory.get("MemAvailable", memory.get("MemFree", 0))
    memory_percent = _percentage(total_memory - available_memory, total_memory)

    disk = shutil.disk_usage("/")
    interfaces = sorted(name for _, name in socket.if_nameindex())
    return SystemSnapshot(
        hostname=socket.gethostname(),
        device_model=_read_text(Path("/proc/device-tree/model")),
        os_version=platform.platform(),
        uptime_seconds=uptime,
        cpu_temperature_c=temperature,
        cpu_utilization_pct=cpu_percent,
        memory_utilization_pct=memory_percent,
        disk_utilization_pct=_percentage(disk.used, disk.total),
        network_interfaces=interfaces,
    )


class HeartbeatCollector:
    """Report system health, collection failures, and durable queue depth."""

    name = "heartbeat"

    def __init__(
        self,
        interval_seconds: float,
        agent_version: str,
        queue_depth: Callable[[], int],
        collection_errors: Callable[[], list[str]],
        probe: SystemProbe = collect_system_snapshot,
    ) -> None:
        self.interval_seconds = interval_seconds
        self._agent_version = agent_version
        self._queue_depth = queue_depth
        self._collection_errors = collection_errors
        self._probe = probe

    def collect(self) -> list[CollectedEvent]:
        snapshot = self._probe()
        return [
            CollectedEvent(
                "network.agent_heartbeat",
                {
                    "hostname": snapshot.hostname,
                    "agent_version": self._agent_version,
                    "device_model": snapshot.device_model,
                    "os_version": snapshot.os_version,
                    "uptime_seconds": snapshot.uptime_seconds,
                    "cpu_temperature_c": snapshot.cpu_temperature_c,
                    "cpu_utilization_pct": snapshot.cpu_utilization_pct,
                    "memory_utilization_pct": snapshot.memory_utilization_pct,
                    "disk_utilization_pct": snapshot.disk_utilization_pct,
                    "network_interfaces": snapshot.network_interfaces,
                    "collection_errors": self._collection_errors(),
                    "local_queue_depth": self._queue_depth(),
                },
            )
        ]
