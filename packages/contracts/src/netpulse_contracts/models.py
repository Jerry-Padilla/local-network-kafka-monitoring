"""Pydantic representations of the version 1 NetPulse event contracts."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMANTIC_VERSION_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"


class AgentRole(StrEnum):
    """Supported Phase 1 agent roles."""

    WIRED_REFERENCE = "wired_reference"
    WIFI_OBSERVER = "wifi_observer"


class CommonEnvelope(BaseModel):
    """Fields present on every event."""

    model_config = ConfigDict(extra="allow")

    event_id: UUID
    event_type: str
    schema_version: Literal[1]
    agent_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    agent_role: AgentRole
    event_time: datetime
    published_time: datetime
    sequence_number: int = Field(ge=0)
    correlation_id: UUID | None = None
    source_version: str = Field(pattern=SEMANTIC_VERSION_PATTERN)

    @field_validator("event_time", "published_time")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        """Reject naive and non-UTC timestamps."""
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value


class NetworkMeasurement(CommonEnvelope):
    """Ping or Wi-Fi diagnostic result."""

    event_type: Literal["network.measurement"]
    measurement_type: Literal["router_ping", "external_ping", "wifi_diagnostics"]
    target_id: str = Field(min_length=1, max_length=128)
    success: bool
    latency_ms: float | None = Field(default=None, ge=0)
    packet_loss_pct: float = Field(ge=0, le=100)
    jitter_ms: float | None = Field(default=None, ge=0)
    signal_dbm: float | None = Field(default=None, ge=-120, le=0)
    connected: bool | None = None
    error_class: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_success_details(self) -> NetworkMeasurement:
        if not self.success and self.latency_ms is not None:
            raise ValueError("failed measurements must not report latency_ms")
        if self.measurement_type == "wifi_diagnostics" and self.connected is None:
            raise ValueError("wifi diagnostics must report connected")
        return self


class ServiceCheck(CommonEnvelope):
    """DNS or HTTP service-check result."""

    event_type: Literal["network.service_check"]
    check_type: Literal["dns", "http"]
    endpoint_id: str = Field(min_length=1, max_length=128)
    success: bool
    resolver: str | None = Field(default=None, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    lookup_duration_ms: float | None = Field(default=None, ge=0)
    dns_duration_ms: float | None = Field(default=None, ge=0)
    tcp_duration_ms: float | None = Field(default=None, ge=0)
    tls_duration_ms: float | None = Field(default=None, ge=0)
    ttfb_ms: float | None = Field(default=None, ge=0)
    total_duration_ms: float | None = Field(default=None, ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)
    returned_record_count: int | None = Field(default=None, ge=0)
    timeout: bool = False
    error_class: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_check_fields(self) -> ServiceCheck:
        if self.check_type == "dns" and (self.domain is None or self.resolver is None):
            raise ValueError("DNS checks require domain and resolver")
        if self.check_type == "http" and self.total_duration_ms is None and self.success:
            raise ValueError("successful HTTP checks require total_duration_ms")
        return self


class SpeedTest(CommonEnvelope):
    """Optional low-frequency throughput test."""

    event_type: Literal["network.speed_test"]
    provider: str = Field(min_length=1, max_length=128)
    server_id: str | None = Field(default=None, max_length=128)
    success: bool
    download_mbps: float | None = Field(default=None, ge=0)
    upload_mbps: float | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    duration_ms: float = Field(ge=0)
    bytes_transferred: int = Field(ge=0)
    error_class: str | None = Field(default=None, max_length=128)


class AgentHeartbeat(CommonEnvelope):
    """Agent health and runtime metadata."""

    event_type: Literal["network.agent_heartbeat"]
    hostname: str = Field(min_length=1, max_length=255)
    agent_version: str = Field(pattern=SEMANTIC_VERSION_PATTERN)
    device_model: str | None = Field(default=None, max_length=255)
    os_version: str = Field(min_length=1, max_length=255)
    uptime_seconds: float = Field(ge=0)
    cpu_temperature_c: float | None = Field(default=None, ge=-40, le=150)
    cpu_utilization_pct: float = Field(ge=0, le=100)
    memory_utilization_pct: float = Field(ge=0, le=100)
    disk_utilization_pct: float = Field(ge=0, le=100)
    network_interfaces: list[str]
    collection_errors: list[str] = Field(default_factory=list)
    local_queue_depth: int = Field(ge=0)


class Incident(CommonEnvelope):
    """Versioned incident contract reserved for Phase 4 producers."""

    event_type: Literal["network.incident"]
    incident_id: UUID
    incident_type: Literal[
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
    start_time: datetime
    end_time: datetime | None = None
    status: Literal["candidate", "open", "ongoing", "recovering", "resolved"]
    severity: Literal["info", "warning", "critical"]
    confidence_score: float = Field(ge=0, le=1)
    affected_agents: list[str]
    affected_endpoints: list[str]
    evidence: list[dict[str, object]]
    rule_version: str = Field(pattern=SEMANTIC_VERSION_PATTERN)
    peak_latency_ms: float | None = Field(default=None, ge=0)
    maximum_packet_loss_pct: float | None = Field(default=None, ge=0, le=100)
    duration_ms: float | None = Field(default=None, ge=0)
    summary: str = Field(min_length=1, max_length=2048)
    recommended_action: str = Field(min_length=1, max_length=2048)

    @field_validator("start_time", "end_time")
    @classmethod
    def require_incident_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value


Event = Annotated[
    NetworkMeasurement | ServiceCheck | SpeedTest | AgentHeartbeat | Incident,
    Field(discriminator="event_type"),
]
