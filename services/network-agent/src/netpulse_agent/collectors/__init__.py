"""Lightweight, mockable Raspberry Pi collectors."""

from netpulse_agent.collectors.dns import DnsCollector
from netpulse_agent.collectors.heartbeat import HeartbeatCollector
from netpulse_agent.collectors.http import HttpCollector
from netpulse_agent.collectors.ping import PingCollector
from netpulse_agent.collectors.speed_test import SpeedTestCollector
from netpulse_agent.collectors.wifi import WifiCollector

__all__ = [
    "DnsCollector",
    "HeartbeatCollector",
    "HttpCollector",
    "PingCollector",
    "SpeedTestCollector",
    "WifiCollector",
]
