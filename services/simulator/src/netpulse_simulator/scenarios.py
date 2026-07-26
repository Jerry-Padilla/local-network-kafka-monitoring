"""Deterministic scenario fixtures for two-agent telemetry."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from netpulse_contracts.models import (
    AgentHeartbeat,
    AgentRole,
    NetworkMeasurement,
    ServiceCheck,
    SpeedTest,
)
from netpulse_contracts.topics import topic_for_event

WIRED_AGENT_ID = "network-agent-ethernet-01"
WIFI_AGENT_ID = "network-agent-wifi-01"
SOURCE_VERSION = "0.1.0"

SCENARIOS = (
    "healthy",
    "wifi-degradation",
    "wifi-outage",
    "router-outage",
    "isp-outage",
    "dns-outage",
    "external-service-failure",
    "high-latency",
    "packet-loss",
    "agent-shutdown",
    "late-events",
    "duplicate-events",
    "malformed-events",
    "clock-drift",
    "kafka-disconnection",
    "burst-traffic",
)

EXPECTED_CLASSIFICATION = {
    "wifi-degradation": "wifi_degradation",
    "wifi-outage": "wifi_outage",
    "router-outage": "router_unavailable",
    "isp-outage": "isp_outage",
    "dns-outage": "dns_failure",
    "external-service-failure": "external_service_failure",
    "high-latency": "high_latency",
    "packet-loss": "high_packet_loss",
    "agent-shutdown": "agent_offline",
}


@dataclass(frozen=True, slots=True)
class SimulatedRecord:
    """Serialized Kafka record emitted by a scenario."""

    topic: str
    key: str
    value: bytes


class ScenarioGenerator:
    """Generate reproducible event rounds from a named network condition."""

    def __init__(self, seed: int = 42, source_version: str = SOURCE_VERSION) -> None:
        self._seed = seed
        self._random = random.Random(seed)
        self._source_version = source_version
        self._sequences = {WIRED_AGENT_ID: 0, WIFI_AGENT_ID: 0}
        self._round = 0

    def generate_round(self, scenario: str, at: datetime | None = None) -> list[SimulatedRecord]:
        """Generate one round; the same seed and timestamp produce the same bytes."""
        normalized = scenario.lower().replace("_", "-")
        if normalized not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; choose from {', '.join(SCENARIOS)}")

        observed_at = at or datetime.now(UTC)
        if observed_at.tzinfo is None or observed_at.utcoffset() != timedelta(0):
            raise ValueError("scenario timestamp must be timezone-aware UTC")
        self._round += 1

        active_agents = [WIRED_AGENT_ID, WIFI_AGENT_ID]
        if normalized == "agent-shutdown":
            active_agents = [WIRED_AGENT_ID]

        records: list[SimulatedRecord] = []
        for agent_id in active_agents:
            event_time = observed_at
            published_time = observed_at + timedelta(milliseconds=25)
            if normalized == "late-events" and agent_id == WIFI_AGENT_ID:
                event_time -= timedelta(hours=2)
            if normalized == "clock-drift" and agent_id == WIFI_AGENT_ID:
                event_time += timedelta(minutes=10)

            records.extend(self._agent_round(normalized, agent_id, event_time, published_time))

        if normalized == "duplicate-events" and records:
            records.append(records[0])
        if normalized == "malformed-events":
            records.append(
                SimulatedRecord(
                    topic=topic_for_event("network.measurement"),
                    key=WIFI_AGENT_ID,
                    value=b'{"event_type":"network.measurement","broken":',
                )
            )
        return records

    def _agent_round(
        self,
        scenario: str,
        agent_id: str,
        event_time: datetime,
        published_time: datetime,
    ) -> list[SimulatedRecord]:
        role = self._role(agent_id)
        wifi_agent = agent_id == WIFI_AGENT_ID
        router_success = scenario not in {"router-outage"} and not (
            scenario == "wifi-outage" and wifi_agent
        )
        external_success = router_success and scenario != "isp-outage"

        router_latency = self._jittered(2.2 if not wifi_agent else 6.5, 0.4)
        external_latency = self._jittered(18 if not wifi_agent else 26, 2)
        packet_loss = 0.0
        signal_dbm = -57.0
        if scenario == "wifi-degradation" and wifi_agent:
            router_latency = self._jittered(85, 8)
            external_latency = self._jittered(145, 12)
            packet_loss = 18.0
            signal_dbm = -84.0
        elif scenario == "high-latency":
            external_latency = self._jittered(240, 10)
        elif scenario == "packet-loss":
            packet_loss = 35.0

        router = NetworkMeasurement(
            **self._envelope(agent_id, role, "network.measurement", event_time, published_time),
            measurement_type="router_ping",
            target_id="router",
            success=router_success,
            latency_ms=router_latency if router_success else None,
            packet_loss_pct=packet_loss if router_success else 100,
            jitter_ms=self._jittered(0.8, 0.2) if router_success else None,
            error_class=None if router_success else "HostUnreachable",
            error_message=None if router_success else "configured router did not respond",
        )
        external = NetworkMeasurement(
            **self._envelope(agent_id, role, "network.measurement", event_time, published_time),
            measurement_type="external_ping",
            target_id="public-dns-a",
            success=external_success,
            latency_ms=external_latency if external_success else None,
            packet_loss_pct=packet_loss if external_success else 100,
            jitter_ms=self._jittered(2.0, 0.5) if external_success else None,
            error_class=None if external_success else "HostUnreachable",
            error_message=(
                None if external_success else "configured external endpoint did not respond"
            ),
        )
        events: list[NetworkMeasurement | ServiceCheck | AgentHeartbeat | SpeedTest] = [
            router,
            external,
        ]

        if wifi_agent:
            connected = scenario != "wifi-outage"
            events.append(
                NetworkMeasurement(
                    **self._envelope(
                        agent_id, role, "network.measurement", event_time, published_time
                    ),
                    measurement_type="wifi_diagnostics",
                    target_id="wifi-interface",
                    success=connected,
                    latency_ms=None,
                    packet_loss_pct=0 if connected else 100,
                    signal_dbm=signal_dbm if connected else None,
                    connected=connected,
                    error_class=None if connected else "NotAssociated",
                    error_message=None if connected else "wireless interface is not associated",
                )
            )

        dns_success = external_success and scenario != "dns-outage"
        events.append(
            ServiceCheck(
                **self._envelope(
                    agent_id, role, "network.service_check", event_time, published_time
                ),
                check_type="dns",
                endpoint_id="dns-check",
                success=dns_success,
                resolver="public-dns-a",
                domain="example.test",
                lookup_duration_ms=self._jittered(14, 2) if dns_success else None,
                returned_record_count=2 if dns_success else 0,
                timeout=not dns_success,
                error_class=None if dns_success else "DnsTimeout",
            )
        )

        http_success = external_success and dns_success and scenario != "external-service-failure"
        events.append(
            ServiceCheck(
                **self._envelope(
                    agent_id, role, "network.service_check", event_time, published_time
                ),
                check_type="http",
                endpoint_id="example-service",
                success=http_success,
                dns_duration_ms=self._jittered(12, 1) if dns_success else None,
                tcp_duration_ms=self._jittered(18, 2) if http_success else None,
                tls_duration_ms=self._jittered(30, 3) if http_success else None,
                ttfb_ms=self._jittered(65, 5) if http_success else None,
                total_duration_ms=self._jittered(110, 8) if http_success else None,
                http_status=204 if http_success else 503 if external_success else None,
                timeout=not external_success,
                error_class=None if http_success else "ServiceUnavailable",
            )
        )

        events.append(
            AgentHeartbeat(
                **self._envelope(
                    agent_id, role, "network.agent_heartbeat", event_time, published_time
                ),
                hostname=agent_id,
                agent_version=self._source_version,
                device_model="simulated-raspberry-pi",
                os_version="simulated-linux-1",
                uptime_seconds=86_400 + self._round,
                cpu_temperature_c=48.0,
                cpu_utilization_pct=self._jittered(12, 2),
                memory_utilization_pct=self._jittered(32, 2),
                disk_utilization_pct=21.0,
                network_interfaces=["eth0"] if not wifi_agent else ["wlan0"],
                collection_errors=[],
                local_queue_depth=0,
            )
        )

        if self._round % 60 == 0:
            events.append(
                SpeedTest(
                    **self._envelope(
                        agent_id, role, "network.speed_test", event_time, published_time
                    ),
                    provider="simulated-provider",
                    server_id="simulated-server-01",
                    success=external_success,
                    download_mbps=92.0 if external_success else None,
                    upload_mbps=18.0 if external_success else None,
                    latency_ms=external_latency if external_success else None,
                    duration_ms=8_000,
                    bytes_transferred=110_000_000 if external_success else 0,
                    error_class=None if external_success else "ProviderUnavailable",
                )
            )
        return [self._serialize(event) for event in events]

    def _envelope(
        self,
        agent_id: str,
        role: AgentRole,
        event_type: str,
        event_time: datetime,
        published_time: datetime,
    ) -> dict[str, object]:
        sequence = self._sequences[agent_id]
        self._sequences[agent_id] += 1
        event_id = uuid5(
            NAMESPACE_URL,
            f"netpulse:{self._seed}:{agent_id}:{sequence}:{event_type}:{event_time.isoformat()}",
        )
        return {
            "event_id": event_id,
            "event_type": event_type,
            "schema_version": 1,
            "agent_id": agent_id,
            "agent_role": role,
            "event_time": event_time,
            "published_time": published_time,
            "sequence_number": sequence,
            "correlation_id": None,
            "source_version": self._source_version,
        }

    @staticmethod
    def _role(agent_id: str) -> AgentRole:
        return AgentRole.WIRED_REFERENCE if agent_id == WIRED_AGENT_ID else AgentRole.WIFI_OBSERVER

    def _jittered(self, mean: float, spread: float) -> float:
        return round(max(0, self._random.gauss(mean, spread)), 3)

    @staticmethod
    def _serialize(
        event: NetworkMeasurement | ServiceCheck | AgentHeartbeat | SpeedTest,
    ) -> SimulatedRecord:
        payload = json.dumps(
            event.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return SimulatedRecord(
            topic=topic_for_event(event.event_type),
            key=event.agent_id,
            value=payload,
        )
