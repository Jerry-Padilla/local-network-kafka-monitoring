"""Typed contracts for Tableau reporting snapshots and CSV datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping, TypeAlias
from uuid import UUID

CsvValue: TypeAlias = str | int | float | None


@dataclass(frozen=True, slots=True)
class DailyReliabilitySource:
    date_utc: date
    agent_id: str
    agent_role: str | None
    source_kind: str
    measurement_type: str
    total_count: int
    success_count: int
    failure_count: int
    latency_count: int
    latency_sum_ms: float | None
    packet_loss_count: int
    packet_loss_sum_pct: float | None


@dataclass(frozen=True, slots=True)
class IncidentSource:
    incident_id: UUID
    incident_type: str
    start_time: datetime
    end_time: datetime | None
    duration_ms: float
    status: str
    severity: str
    confidence_score: float
    rule_version: str
    state_revision: int
    affected_agent_count: int
    affected_endpoint_count: int


@dataclass(frozen=True, slots=True)
class PipelineHealthSource:
    observed_at: datetime
    last_raw_event_received_at: datetime | None
    raw_event_age_seconds: float | None
    pending_dead_letter_count: int
    stream_processing_failure_count: int
    last_stream_batch_completed_at: datetime | None
    active_incident_count: int
    pending_incident_publication_count: int


@dataclass(frozen=True, slots=True)
class TableauSnapshot:
    daily_reliability: tuple[DailyReliabilitySource, ...] = ()
    incidents: tuple[IncidentSource, ...] = ()
    pipeline_health: PipelineHealthSource | None = None


@dataclass(frozen=True, slots=True)
class CsvDataset:
    columns: tuple[str, ...]
    rows: tuple[tuple[CsvValue, ...], ...]

    def __post_init__(self) -> None:
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("CSV row column count does not match the header")


@dataclass(frozen=True, slots=True)
class ExportBundle:
    datasets: Mapping[str, CsvDataset] = field(default_factory=dict)
