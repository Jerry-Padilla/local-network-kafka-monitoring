"""Environment-backed deterministic classifier configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    bootstrap_servers: str
    database_url: str
    client_id: str
    lookback_seconds: int
    interval_seconds: float
    minimum_samples: int
    open_observations: int
    resolve_observations: int
    healthy_success_rate_pct: float
    failed_success_rate_pct: float
    high_latency_ms: float
    high_packet_loss_pct: float
    weak_signal_dbm: float
    heartbeat_stale_seconds: int
    delivery_timeout_seconds: float

    @classmethod
    def from_env(cls) -> ClassifierConfig:
        config = cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"),
            database_url=os.getenv(
                "NETPULSE_DATABASE_URL",
                "postgresql://netpulse_app:change-me-local-app@localhost:5432/netpulse",
            ),
            client_id=os.getenv("NETPULSE_CLASSIFIER_CLIENT_ID", "netpulse-classifier"),
            lookback_seconds=int(os.getenv("NETPULSE_CLASSIFIER_LOOKBACK_SECONDS", "60")),
            interval_seconds=float(os.getenv("NETPULSE_CLASSIFIER_INTERVAL_SECONDS", "10")),
            minimum_samples=int(os.getenv("NETPULSE_CLASSIFIER_MINIMUM_SAMPLES", "2")),
            open_observations=int(os.getenv("NETPULSE_CLASSIFIER_OPEN_OBSERVATIONS", "2")),
            resolve_observations=int(os.getenv("NETPULSE_CLASSIFIER_RESOLVE_OBSERVATIONS", "2")),
            healthy_success_rate_pct=float(
                os.getenv("NETPULSE_CLASSIFIER_HEALTHY_SUCCESS_PCT", "80")
            ),
            failed_success_rate_pct=float(
                os.getenv("NETPULSE_CLASSIFIER_FAILED_SUCCESS_PCT", "20")
            ),
            high_latency_ms=float(os.getenv("NETPULSE_CLASSIFIER_HIGH_LATENCY_MS", "150")),
            high_packet_loss_pct=float(os.getenv("NETPULSE_CLASSIFIER_HIGH_PACKET_LOSS_PCT", "20")),
            weak_signal_dbm=float(os.getenv("NETPULSE_CLASSIFIER_WEAK_SIGNAL_DBM", "-78")),
            heartbeat_stale_seconds=int(
                os.getenv("NETPULSE_CLASSIFIER_HEARTBEAT_STALE_SECONDS", "150")
            ),
            delivery_timeout_seconds=float(os.getenv("NETPULSE_DELIVERY_TIMEOUT_SECONDS", "10")),
        )
        positive = (
            config.lookback_seconds,
            config.minimum_samples,
            config.open_observations,
            config.resolve_observations,
            config.heartbeat_stale_seconds,
        )
        if any(value < 1 for value in positive):
            raise ValueError("classifier counts and time windows must be positive")
        if config.interval_seconds <= 0 or config.delivery_timeout_seconds <= 0:
            raise ValueError("classifier intervals and timeouts must be positive")
        if not (0 <= config.failed_success_rate_pct < config.healthy_success_rate_pct <= 100):
            raise ValueError("success thresholds must be ordered within 0..100")
        if config.high_latency_ms <= 0 or not 0 <= config.high_packet_loss_pct <= 100:
            raise ValueError("anomaly thresholds are outside supported ranges")
        if not -120 <= config.weak_signal_dbm <= 0:
            raise ValueError("weak signal threshold must be between -120 and 0 dBm")
        return config
