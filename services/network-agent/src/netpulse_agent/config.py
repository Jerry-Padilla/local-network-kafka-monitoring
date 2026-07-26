"""YAML and environment-backed agent configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from netpulse_contracts.models import AgentRole
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class AgentIdentityConfig(BaseModel):
    """Stable identity included in every event envelope."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$", max_length=128)
    role: AgentRole
    source_version: str = "0.2.0"


class KafkaConfig(BaseModel):
    """Kafka delivery settings suitable for a constrained agent."""

    model_config = ConfigDict(extra="forbid")

    bootstrap_servers: str = "localhost:29092"
    client_id: str = "netpulse-network-agent"
    compression: Literal["zstd", "gzip", "snappy", "lz4", "none"] = "zstd"
    delivery_timeout_seconds: float = Field(default=10, gt=0, le=300)
    poll_interval_seconds: float = Field(default=1, gt=0, le=60)


class OutboxConfig(BaseModel):
    """Durable queue limits and retry policy."""

    model_config = ConfigDict(extra="forbid")

    path: Path = Path("/var/lib/netpulse-agent/outbox.db")
    maximum_bytes: int = Field(default=268_435_456, ge=1_048_576)
    batch_size: int = Field(default=50, ge=1, le=1_000)
    retry_base_seconds: float = Field(default=1, gt=0, le=300)
    retry_max_seconds: float = Field(default=300, gt=0, le=86_400)
    acknowledged_retention_seconds: int = Field(default=86_400, ge=0)

    @model_validator(mode="after")
    def retry_ceiling_must_exceed_base(self) -> OutboxConfig:
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("retry_max_seconds must be at least retry_base_seconds")
        return self


class PrivacyConfig(BaseModel):
    """Controls potentially sensitive Wi-Fi identifiers."""

    model_config = ConfigDict(extra="forbid")

    ssid: Literal["omit", "hash", "plain"] = "omit"
    bssid: Literal["omit", "hash", "plain"] = "omit"
    hash_salt: str = Field(default="replace-this-local-salt", min_length=8)
    include_target_addresses: bool = False


class EndpointConfig(BaseModel):
    """Explicitly allowed endpoint and safe reporting alias."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str = Field(min_length=1, max_length=128)
    address: str = Field(min_length=1, max_length=512)


class PingCollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: float = Field(default=5, gt=0)
    sample_count: int = Field(default=3, ge=1, le=20)
    timeout_seconds: float = Field(default=2, gt=0, le=60)
    endpoints: list[EndpointConfig] = Field(default_factory=list)


class DnsEndpointConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=255)
    resolver: str = Field(min_length=1, max_length=255)
    record_type: Literal["A", "AAAA"] = "A"


class DnsCollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: float = Field(default=15, gt=0)
    timeout_seconds: float = Field(default=3, gt=0, le=60)
    endpoints: list[DnsEndpointConfig] = Field(default_factory=list)


class HttpCollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: float = Field(default=30, gt=0)
    timeout_seconds: float = Field(default=5, gt=0, le=120)
    maximum_body_bytes: int = Field(default=1_024, ge=0, le=65_536)
    endpoints: list[EndpointConfig] = Field(default_factory=list)

    @field_validator("endpoints")
    @classmethod
    def require_http_urls(cls, endpoints: list[EndpointConfig]) -> list[EndpointConfig]:
        for endpoint in endpoints:
            if not endpoint.address.startswith(("http://", "https://")):
                raise ValueError(f"{endpoint.endpoint_id} must use http:// or https://")
        return endpoints


class WifiCollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: float = Field(default=10, gt=0)
    endpoint_id: str = Field(default="wifi-interface", min_length=1, max_length=128)
    interface: str = Field(default="wlan0", pattern=r"^[a-zA-Z0-9_.:-]+$")


class HeartbeatCollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: float = Field(default=60, gt=0)


class SpeedTestCollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    interval_seconds: float = Field(default=3_600, ge=300)
    provider: Literal["speedtest-cli"] = "speedtest-cli"
    server_id: str | None = Field(default=None, max_length=128)
    timeout_seconds: float = Field(default=180, gt=0, le=900)


class CollectorsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    router_ping: PingCollectorConfig = Field(default_factory=PingCollectorConfig)
    external_ping: PingCollectorConfig = Field(default_factory=PingCollectorConfig)
    dns: DnsCollectorConfig = Field(default_factory=DnsCollectorConfig)
    http: HttpCollectorConfig = Field(default_factory=HttpCollectorConfig)
    wifi: WifiCollectorConfig = Field(default_factory=WifiCollectorConfig)
    heartbeat: HeartbeatCollectorConfig = Field(default_factory=HeartbeatCollectorConfig)
    speed_test: SpeedTestCollectorConfig = Field(default_factory=SpeedTestCollectorConfig)


class AgentConfig(BaseModel):
    """Complete validated configuration."""

    model_config = ConfigDict(extra="forbid")

    agent: AgentIdentityConfig
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    outbox: OutboxConfig = Field(default_factory=OutboxConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    collectors: CollectorsConfig = Field(default_factory=CollectorsConfig)


class AgentConfigurationError(ValueError):
    """Configuration cannot be loaded or validated."""


_ENVIRONMENT_OVERRIDES: dict[str, tuple[str, ...]] = {
    "NETPULSE_AGENT_ID": ("agent", "agent_id"),
    "NETPULSE_AGENT_ROLE": ("agent", "role"),
    "NETPULSE_SOURCE_VERSION": ("agent", "source_version"),
    "KAFKA_BOOTSTRAP_SERVERS": ("kafka", "bootstrap_servers"),
    "NETPULSE_AGENT_CLIENT_ID": ("kafka", "client_id"),
    "NETPULSE_OUTBOX_PATH": ("outbox", "path"),
    "NETPULSE_OUTBOX_MAXIMUM_BYTES": ("outbox", "maximum_bytes"),
    "NETPULSE_PRIVACY_HASH_SALT": ("privacy", "hash_salt"),
}


def _set_nested(candidate: dict[str, Any], path: tuple[str, ...], value: str) -> None:
    current = candidate
    for segment in path[:-1]:
        nested = current.setdefault(segment, {})
        if not isinstance(nested, dict):
            raise AgentConfigurationError(f"cannot override non-object configuration at {segment}")
        current = nested
    current[path[-1]] = value


def load_config(
    path: str | Path,
    environ: Mapping[str, str] | None = None,
) -> AgentConfig:
    """Load YAML and apply a small, explicit environment override allowlist."""
    config_path = Path(path)
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise AgentConfigurationError(f"unable to read {config_path}: {error}") from error
    if not isinstance(loaded, dict):
        raise AgentConfigurationError("agent configuration must be a YAML object")

    candidate: dict[str, Any] = dict(loaded)
    environment = os.environ if environ is None else environ
    for variable, nested_path in _ENVIRONMENT_OVERRIDES.items():
        if variable in environment:
            _set_nested(candidate, nested_path, environment[variable])
    try:
        return AgentConfig.model_validate(candidate)
    except ValidationError as error:
        raise AgentConfigurationError(str(error)) from error
