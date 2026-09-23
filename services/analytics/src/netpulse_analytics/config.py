"""Environment-backed analytics job configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalyticsConfig:
    database_url: str

    @classmethod
    def from_env(cls) -> AnalyticsConfig:
        database_url = os.getenv("NETPULSE_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("NETPULSE_DATABASE_URL is required")
        return cls(database_url=database_url)
