"""Environment-backed ingestion configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IngestionConfig:
    bootstrap_servers: str
    database_url: str
    consumer_group: str
    client_id: str
    max_processing_attempts: int
    retry_base_seconds: float
    delivery_timeout_seconds: float

    @classmethod
    def from_env(cls) -> IngestionConfig:
        config = cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"),
            database_url=os.getenv(
                "NETPULSE_DATABASE_URL",
                "postgresql://netpulse_app:change-me-local-app@localhost:5432/netpulse",
            ),
            consumer_group=os.getenv("NETPULSE_CONSUMER_GROUP", "netpulse-ingestion-v1"),
            client_id=os.getenv("NETPULSE_INGESTOR_CLIENT_ID", "netpulse-event-ingestor"),
            max_processing_attempts=int(os.getenv("NETPULSE_MAX_PROCESSING_ATTEMPTS", "5")),
            retry_base_seconds=float(os.getenv("NETPULSE_RETRY_BASE_SECONDS", "0.5")),
            delivery_timeout_seconds=float(os.getenv("NETPULSE_DELIVERY_TIMEOUT_SECONDS", "10")),
        )
        if config.max_processing_attempts < 1:
            raise ValueError("NETPULSE_MAX_PROCESSING_ATTEMPTS must be at least 1")
        if config.retry_base_seconds <= 0 or config.delivery_timeout_seconds <= 0:
            raise ValueError("retry and delivery timeouts must be positive")
        return config
