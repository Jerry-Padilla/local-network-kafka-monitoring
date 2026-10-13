"""Pure transformations from reporting snapshots to Tableau CSV datasets."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime

from netpulse_analytics.tableau.models import (
    CsvDataset,
    DailyReliabilitySource,
    ExportBundle,
    IncidentSource,
    PipelineHealthSource,
    TableauSnapshot,
)

_AGENT_NAMESPACE = b"netpulse-tableau-agent-v1\0"

DAILY_COLUMNS = (
    "date_utc",
    "agent_key",
    "agent_role",
    "source_kind",
    "measurement_type",
    "total_probes",
    "successful_probes",
    "failed_probes",
    "success_rate_pct",
    "average_latency_ms",
    "average_packet_loss_pct",
)
AGENT_COLUMNS = (
    "agent_key",
    "agent_role",
    "source_kind",
    "measurement_type",
    "first_observation_date",
    "latest_observation_date",
    "observation_day_count",
    "total_probes",
    "successful_probes",
    "failed_probes",
    "success_rate_pct",
    "average_latency_ms",
    "average_packet_loss_pct",
)
INCIDENT_COLUMNS = (
    "incident_id",
    "incident_type",
    "start_time_utc",
    "end_time_utc",
    "duration_ms",
    "status",
    "severity",
    "confidence_score",
    "rule_version",
    "state_revision",
    "affected_agent_count",
    "affected_endpoint_count",
)
PIPELINE_COLUMNS = (
    "observed_at_utc",
    "last_raw_event_received_at_utc",
    "raw_event_age_seconds",
    "pending_dead_letter_count",
    "stream_processing_failure_count",
    "last_stream_batch_completed_at_utc",
    "active_incident_count",
    "pending_incident_publication_count",
)


def pseudonymize_agent(agent_id: str) -> str:
    digest = hashlib.sha256(_AGENT_NAMESPACE + agent_id.encode("utf-8")).hexdigest()
    return f"agent_{digest[:12]}"


def _ratio(numerator: float, denominator: int, multiplier: float = 1.0) -> float | None:
    if denominator == 0:
        return None
    return multiplier * numerator / denominator


def _daily_groups(
    rows: Iterable[DailyReliabilitySource],
) -> dict[tuple[date, str, str | None, str, str], list[DailyReliabilitySource]]:
    groups: dict[tuple[date, str, str | None, str, str], list[DailyReliabilitySource]] = (
        defaultdict(list)
    )
    for row in rows:
        key = (
            row.date_utc,
            pseudonymize_agent(row.agent_id),
            row.agent_role,
            row.source_kind,
            row.measurement_type,
        )
        groups[key].append(row)
    return groups


def _daily_dataset(rows: tuple[DailyReliabilitySource, ...]) -> CsvDataset:
    output = []
    groups = _daily_groups(rows)
    for key in sorted(groups, key=lambda item: (item[0], item[1], item[2] or "", *item[3:])):
        date_utc, agent_key, agent_role, source_kind, measurement_type = key
        members = groups[key]
        total = sum(row.total_count for row in members)
        successes = sum(row.success_count for row in members)
        failures = sum(row.failure_count for row in members)
        latency_count = sum(row.latency_count for row in members)
        latency_sum = sum(row.latency_sum_ms or 0.0 for row in members)
        loss_count = sum(row.packet_loss_count for row in members)
        loss_sum = sum(row.packet_loss_sum_pct or 0.0 for row in members)
        output.append(
            (
                date_utc.isoformat(),
                agent_key,
                agent_role,
                source_kind,
                measurement_type,
                total,
                successes,
                failures,
                _ratio(float(successes), total, 100.0),
                _ratio(latency_sum, latency_count),
                _ratio(loss_sum, loss_count),
            )
        )
    return CsvDataset(columns=DAILY_COLUMNS, rows=tuple(output))


def _agent_dataset(rows: tuple[DailyReliabilitySource, ...]) -> CsvDataset:
    groups: dict[tuple[str, str | None, str, str], list[DailyReliabilitySource]] = defaultdict(list)
    for row in rows:
        groups[
            (
                pseudonymize_agent(row.agent_id),
                row.agent_role,
                row.source_kind,
                row.measurement_type,
            )
        ].append(row)

    output = []
    for key in sorted(groups, key=lambda item: (item[0], item[1] or "", *item[2:])):
        agent_key, agent_role, source_kind, measurement_type = key
        members = groups[key]
        dates = {row.date_utc for row in members}
        total = sum(row.total_count for row in members)
        successes = sum(row.success_count for row in members)
        failures = sum(row.failure_count for row in members)
        latency_count = sum(row.latency_count for row in members)
        latency_sum = sum(row.latency_sum_ms or 0.0 for row in members)
        loss_count = sum(row.packet_loss_count for row in members)
        loss_sum = sum(row.packet_loss_sum_pct or 0.0 for row in members)
        output.append(
            (
                agent_key,
                agent_role,
                source_kind,
                measurement_type,
                min(dates).isoformat(),
                max(dates).isoformat(),
                len(dates),
                total,
                successes,
                failures,
                _ratio(float(successes), total, 100.0),
                _ratio(latency_sum, latency_count),
                _ratio(loss_sum, loss_count),
            )
        )
    return CsvDataset(columns=AGENT_COLUMNS, rows=tuple(output))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("export timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    utc_value = _as_utc(value)
    timespec = "microseconds" if utc_value.microsecond else "seconds"
    return utc_value.isoformat(timespec=timespec).replace("+00:00", "Z")


def _incident_dataset(rows: tuple[IncidentSource, ...]) -> CsvDataset:
    by_id: dict[object, IncidentSource] = {}
    for row in rows:
        previous = by_id.get(row.incident_id)
        if previous is not None and previous != row:
            raise ValueError(f"conflicting duplicate incident: {row.incident_id}")
        by_id[row.incident_id] = row

    output = []
    for row in sorted(
        by_id.values(), key=lambda item: (_as_utc(item.start_time), item.incident_id)
    ):
        output.append(
            (
                str(row.incident_id),
                row.incident_type,
                _format_utc(row.start_time),
                _format_utc(row.end_time),
                row.duration_ms,
                row.status,
                row.severity,
                row.confidence_score,
                row.rule_version,
                row.state_revision,
                row.affected_agent_count,
                row.affected_endpoint_count,
            )
        )
    return CsvDataset(columns=INCIDENT_COLUMNS, rows=tuple(output))


def _pipeline_dataset(row: PipelineHealthSource | None) -> CsvDataset:
    if row is None:
        return CsvDataset(columns=PIPELINE_COLUMNS, rows=())
    return CsvDataset(
        columns=PIPELINE_COLUMNS,
        rows=(
            (
                _format_utc(row.observed_at),
                _format_utc(row.last_raw_event_received_at),
                row.raw_event_age_seconds,
                row.pending_dead_letter_count,
                row.stream_processing_failure_count,
                _format_utc(row.last_stream_batch_completed_at),
                row.active_incident_count,
                row.pending_incident_publication_count,
            ),
        ),
    )


def build_export_bundle(snapshot: TableauSnapshot) -> ExportBundle:
    return ExportBundle(
        datasets={
            "daily_reliability.csv": _daily_dataset(snapshot.daily_reliability),
            "incidents.csv": _incident_dataset(snapshot.incidents),
            "agent_performance.csv": _agent_dataset(snapshot.daily_reliability),
            "pipeline_health.csv": _pipeline_dataset(snapshot.pipeline_health),
        }
    )
