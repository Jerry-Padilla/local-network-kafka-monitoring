"""Environment-backed simulator configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulatorConfig:
    """Kafka and reproducibility settings."""

    bootstrap_servers: str = "localhost:29092"
    seed: int = 42
    client_id: str = "netpulse-simulator"
    source_version: str = "0.1.0"

    @classmethod
    def from_env(cls) -> SimulatorConfig:
        return cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"),
            seed=int(os.getenv("NETPULSE_SIMULATOR_SEED", "42")),
            client_id=os.getenv("NETPULSE_SIMULATOR_CLIENT_ID", "netpulse-simulator"),
            source_version=os.getenv("NETPULSE_SOURCE_VERSION", "0.1.0"),
        )
