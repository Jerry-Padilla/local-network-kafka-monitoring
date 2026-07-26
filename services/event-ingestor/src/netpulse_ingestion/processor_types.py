"""Dependency-light ingestion value types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Kafka source coordinates and original data."""

    topic: str
    partition: int
    offset: int
    key: str | None
    value: bytes
