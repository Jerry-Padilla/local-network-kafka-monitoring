"""Small domain models used by the deterministic classifier."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

IncidentType = Literal[
    "wifi_degradation",
    "wifi_outage",
    "router_unavailable",
    "isp_outage",
    "dns_failure",
    "external_service_failure",
    "high_latency",
    "high_packet_loss",
    "agent_offline",
    "unknown_network_incident",
]
IncidentStatus = Literal["candidate", "open", "ongoing", "recovering", "resolved"]
Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True, slots=True)
class MeasurementSummary:
    agent_id: str
    agent_role: str
    target_id: str
    measurement_type: str
    sample_count: int
    success_rate_pct: float
    peak_latency_ms: float | None
    mean_packet_loss_pct: float
    weakest_signal_dbm: float | None = None
    connected_rate_pct: float | None = None


@dataclass(frozen=True, slots=True)
class ServiceSummary:
    agent_id: str
    agent_role: str
    endpoint_id: str
    check_type: str
    sample_count: int
    success_rate_pct: float


@dataclass(frozen=True, slots=True)
class HeartbeatSummary:
    agent_id: str
    agent_role: str
    last_event_time: datetime | None


@dataclass(frozen=True, slots=True)
class ObservationSnapshot:
    observed_at: datetime
    measurements: tuple[MeasurementSummary, ...]
    services: tuple[ServiceSummary, ...]
    heartbeats: tuple[HeartbeatSummary, ...]


@dataclass(frozen=True, slots=True)
class Finding:
    incident_key: str
    incident_type: IncidentType
    severity: Severity
    confidence_score: float
    affected_agents: tuple[str, ...]
    affected_endpoints: tuple[str, ...]
    evidence: tuple[dict[str, object], ...]
    peak_latency_ms: float | None
    maximum_packet_loss_pct: float | None
    summary: str
    recommended_action: str


@dataclass(frozen=True, slots=True)
class ActiveIncident:
    incident_id: UUID
    incident_key: str
    incident_type: IncidentType
    start_time: datetime
    status: IncidentStatus
    state_revision: int
    positive_observations: int
    recovery_observations: int
    finding: Finding


@dataclass(frozen=True, slots=True)
class Transition:
    incident_id: UUID
    finding: Finding
    start_time: datetime
    end_time: datetime | None
    status: IncidentStatus
    state_revision: int
    positive_observations: int
    recovery_observations: int
