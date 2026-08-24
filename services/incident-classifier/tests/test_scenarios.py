from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import pytest
from netpulse_classifier.config import ClassifierConfig
from netpulse_classifier.engine import ClassificationEngine
from netpulse_classifier.models import (
    HeartbeatSummary,
    MeasurementSummary,
    ObservationSnapshot,
    ServiceSummary,
)
from netpulse_contracts.models import AgentHeartbeat, NetworkMeasurement, ServiceCheck
from netpulse_contracts.validation import validate_event
from netpulse_simulator.scenarios import (
    EXPECTED_CLASSIFICATION,
    WIFI_AGENT_ID,
    WIRED_AGENT_ID,
    ScenarioGenerator,
)

AT = datetime(2026, 7, 26, 15, tzinfo=UTC)


def _config() -> ClassifierConfig:
    return ClassifierConfig(
        bootstrap_servers="unused",
        database_url="unused",
        client_id="scenario-test",
        lookback_seconds=60,
        interval_seconds=10,
        minimum_samples=2,
        open_observations=2,
        resolve_observations=2,
        healthy_success_rate_pct=80,
        failed_success_rate_pct=20,
        high_latency_ms=150,
        high_packet_loss_pct=20,
        weak_signal_dbm=-78,
        heartbeat_stale_seconds=150,
        delivery_timeout_seconds=1,
    )


def _snapshot(scenario: str) -> ObservationSnapshot:
    generator = ScenarioGenerator(seed=91)
    measurements: defaultdict[tuple[str, str, str, str], list[NetworkMeasurement]]
    measurements = defaultdict(list)
    services: defaultdict[tuple[str, str, str, str], list[ServiceCheck]]
    services = defaultdict(list)
    heartbeat_times: dict[tuple[str, str], datetime] = {}
    for _ in range(3):
        for record in generator.generate_round(scenario, AT):
            event = validate_event(record.value)
            if isinstance(event, NetworkMeasurement):
                measurements[
                    (
                        event.agent_id,
                        event.agent_role.value,
                        event.target_id,
                        event.measurement_type,
                    )
                ].append(event)
            elif isinstance(event, ServiceCheck):
                services[
                    (
                        event.agent_id,
                        event.agent_role.value,
                        event.endpoint_id,
                        event.check_type,
                    )
                ].append(event)
            elif isinstance(event, AgentHeartbeat):
                heartbeat_times[(event.agent_id, event.agent_role.value)] = event.event_time

    measurement_summaries = tuple(
        MeasurementSummary(
            agent_id=key[0],
            agent_role=key[1],
            target_id=key[2],
            measurement_type=key[3],
            sample_count=len(values),
            success_rate_pct=sum(100 for value in values if value.success) / len(values),
            peak_latency_ms=max(
                (value.latency_ms for value in values if value.latency_ms is not None),
                default=None,
            ),
            mean_packet_loss_pct=sum(value.packet_loss_pct for value in values) / len(values),
            weakest_signal_dbm=min(
                (value.signal_dbm for value in values if value.signal_dbm is not None),
                default=None,
            ),
            connected_rate_pct=(
                sum(100 for value in values if value.connected) / len(values)
                if any(value.connected is not None for value in values)
                else None
            ),
        )
        for key, values in measurements.items()
    )
    service_summaries = tuple(
        ServiceSummary(
            agent_id=key[0],
            agent_role=key[1],
            endpoint_id=key[2],
            check_type=key[3],
            sample_count=len(values),
            success_rate_pct=sum(100 for value in values if value.success) / len(values),
        )
        for key, values in services.items()
    )
    roles = {
        WIRED_AGENT_ID: "wired_reference",
        WIFI_AGENT_ID: "wifi_observer",
    }
    heartbeats = tuple(
        HeartbeatSummary(
            agent_id,
            role,
            heartbeat_times.get((agent_id, role)),
        )
        for agent_id, role in roles.items()
    )
    return ObservationSnapshot(AT, measurement_summaries, service_summaries, heartbeats)


@pytest.mark.parametrize(
    ("scenario", "expected"),
    sorted(EXPECTED_CLASSIFICATION.items()),
)
def test_simulator_scenario_has_expected_deterministic_classification(
    scenario: str, expected: str
) -> None:
    findings = ClassificationEngine(_config()).classify(_snapshot(scenario))

    assert expected in {finding.incident_type for finding in findings}
