"""Typed environment configuration for the query API."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class QueryApiConfig:
    database_url: str = field(repr=False)
    pool_min_size: int = 1
    pool_max_size: int = 5
    pool_acquire_timeout_seconds: float = 2.0
    statement_timeout_ms: int = 3000
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if not self.database_url.strip():
            raise ValueError("NETPULSE_DATABASE_URL is required")
        if self.pool_min_size < 1:
            raise ValueError("pool minimum must be at least 1")
        if self.pool_max_size < self.pool_min_size:
            raise ValueError("pool maximum must be at least the minimum")
        if (
            not math.isfinite(self.pool_acquire_timeout_seconds)
            or self.pool_acquire_timeout_seconds <= 0
        ):
            raise ValueError("pool acquire timeout must be positive and finite")
        if self.statement_timeout_ms <= 0:
            raise ValueError("statement timeout must be positive")

    @classmethod
    def from_env(cls) -> QueryApiConfig:
        return cls(
            database_url=os.getenv("NETPULSE_DATABASE_URL", "").strip(),
            pool_min_size=int(os.getenv("NETPULSE_QUERY_API_POOL_MIN_SIZE", "1")),
            pool_max_size=int(os.getenv("NETPULSE_QUERY_API_POOL_MAX_SIZE", "5")),
            pool_acquire_timeout_seconds=float(
                os.getenv("NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS", "2.0")
            ),
            statement_timeout_ms=int(os.getenv("NETPULSE_QUERY_API_STATEMENT_TIMEOUT_MS", "3000")),
            log_level=os.getenv("NETPULSE_QUERY_API_LOG_LEVEL", "INFO"),
        )
