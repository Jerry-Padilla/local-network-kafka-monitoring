"""Environment-backed analytics job configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AnalyticsConfig:
    database_url: str

    @classmethod
    def from_env(cls) -> AnalyticsConfig:
        database_url = os.getenv("NETPULSE_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("NETPULSE_DATABASE_URL is required")
        return cls(database_url=database_url)


@dataclass(frozen=True, slots=True)
class TableauExportConfig:
    database_url: str
    output_dir: Path

    @classmethod
    def from_env(cls, output_dir: Path) -> TableauExportConfig:
        database_url = os.getenv("NETPULSE_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("NETPULSE_DATABASE_URL is required")
        return cls(database_url=database_url, output_dir=output_dir)
