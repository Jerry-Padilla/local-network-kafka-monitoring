#!/usr/bin/env python3
"""Validate the promoted Tableau CSV bundle without exposing its contents."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path

EXPECTED_HEADERS: dict[str, tuple[str, ...]] = {
    "daily_reliability.csv": (
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
    ),
    "incidents.csv": (
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
    ),
    "agent_performance.csv": (
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
    ),
    "pipeline_health.csv": (
        "observed_at_utc",
        "last_raw_event_received_at_utc",
        "raw_event_age_seconds",
        "pending_dead_letter_count",
        "stream_processing_failure_count",
        "last_stream_batch_completed_at_utc",
        "active_incident_count",
        "pending_incident_publication_count",
    ),
}


def verify_export(output_dir: Path) -> dict[str, int]:
    actual_files = {path.name for path in output_dir.glob("*.csv")}
    expected_files = set(EXPECTED_HEADERS)
    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing datasets: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected datasets: {', '.join(unexpected)}")
        raise ValueError("; ".join(details))

    row_counts: dict[str, int] = {}
    for filename in sorted(EXPECTED_HEADERS):
        with (output_dir / filename).open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = tuple(next(reader, ()))
            if header != EXPECTED_HEADERS[filename]:
                raise ValueError(f"{filename} has an unexpected header")
            row_counts[filename] = sum(1 for _ in reader)
    if row_counts["pipeline_health.csv"] != 1:
        raise ValueError("pipeline_health.csv must contain exactly one snapshot row")
    return row_counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(verify_export(args.output_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
