from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from netpulse_classifier.config import ClassifierConfig
from netpulse_classifier.engine import ClassificationEngine
from netpulse_classifier.models import (
    ActiveIncident,
    HeartbeatSummary,
    MeasurementSummary,
    ObservationSnapshot,
    ServiceSummary,
)

AT = datetime(2026, 7, 26, 12, tzinfo=UTC)
WIRED = "network-agent-ethernet-01"
WIFI = "network-agent-wifi-01"


def config(**overrides: object) -> ClassifierConfig:
    values: dict[str, object] = {
        "bootstrap_servers": "broker:9092",
        "database_url": "postgresql://example",
        "client_id": "test-classifier",
        "lookback_seconds": 60,
        "interval_seconds": 10.0,
        "minimum_samples": 2,
        "open_observations": 2,
        "resolve_observations": 2,
        "healthy_success_rate_pct": 80.0,
        "failed_success_rate_pct": 20.0,
        "high_latency_ms": 150.0,
        "high_packet_loss_pct": 20.0,
        "weak_signal_dbm": -78.0,
        "heartbeat_stale_seconds": 150,
        "delivery_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return ClassifierConfig(**values)  # type: ignore[arg-type]


def measurement(
    agent_id: str,
    role: str,
    measurement_type: str,
    target_id: str,
    *,
    samples: int = 5,
    success: float = 100,
    latency: float | None = 25,
    loss: float = 0,
    signal: float | None = None,
    connected: float | None = None,
) -> MeasurementSummary:
    return MeasurementSummary(
        agent_id,
        role,
        target_id,
        measurement_type,
        samples,
        success,
        latency,
        loss,
        signal,
        connected,
    )


def service(
    agent_id: str,
    role: str,
    check_type: str,
    endpoint_id: str,
    *,
    samples: int = 5,
    success: float = 100,
) -> ServiceSummary:
    return ServiceSummary(agent_id, role, endpoint_id, check_type, samples, success)


def healthy_snapshot() -> ObservationSnapshot:
    measurements = (
        measurement(WIRED, "wired_reference", "router_ping", "router", latency=2),
        measurement(WIFI, "wifi_observer", "router_ping", "router", latency=6),
        measurement(WIRED, "wired_reference", "external_ping", "public-dns-a", latency=18),
        measurement(WIFI, "wifi_observer", "external_ping", "public-dns-a", latency=26),
        measurement(
            WIFI,
            "wifi_observer",
            "wifi_diagnostics",
            "wifi-interface",
            latency=None,
            signal=-57,
            connected=100,
        ),
    )
    services = (
        service(WIRED, "wired_reference", "dns", "dns-check"),
        service(WIFI, "wifi_observer", "dns", "dns-check"),
        service(WIRED, "wired_reference", "http", "example-service"),
        service(WIFI, "wifi_observer", "http", "example-service"),
    )
    heartbeats = (
        HeartbeatSummary(WIRED, "wired_reference", AT),
        HeartbeatSummary(WIFI, "wifi_observer", AT),
    )
    return ObservationSnapshot(AT, measurements, services, heartbeats)


def replace_measurements(
    snapshot: ObservationSnapshot,
    replacements: dict[tuple[str, str], MeasurementSummary],
) -> ObservationSnapshot:
    values = tuple(
        replacements.get((item.agent_id, item.measurement_type), item)
        for item in snapshot.measurements
    )
    return ObservationSnapshot(snapshot.observed_at, values, snapshot.services, snapshot.heartbeats)


def incident_types(snapshot: ObservationSnapshot) -> set[str]:
    return {finding.incident_type for finding in ClassificationEngine(config()).classify(snapshot)}


def test_healthy_observations_do_not_create_incident() -> None:
    assert incident_types(healthy_snapshot()) == set()


def test_wifi_degradation_requires_wired_baseline_and_wifi_evidence() -> None:
    snapshot = healthy_snapshot()
    degraded = replace_measurements(
        snapshot,
        {
            (WIFI, "router_ping"): measurement(
                WIFI,
                "wifi_observer",
                "router_ping",
                "router",
                latency=85,
                loss=18,
            ),
            (WIFI, "wifi_diagnostics"): measurement(
                WIFI,
                "wifi_observer",
                "wifi_diagnostics",
                "wifi-interface",
                latency=None,
                signal=-84,
                connected=100,
            ),
        },
    )

    assert incident_types(degraded) == {"wifi_degradation"}


def test_wifi_outage_requires_wired_health_and_disassociation() -> None:
    snapshot = replace_measurements(
        healthy_snapshot(),
        {
            (WIFI, "router_ping"): measurement(
                WIFI, "wifi_observer", "router_ping", "router", success=0, latency=None, loss=100
            ),
            (WIFI, "wifi_diagnostics"): measurement(
                WIFI,
                "wifi_observer",
                "wifi_diagnostics",
                "wifi-interface",
                success=0,
                latency=None,
                loss=100,
                connected=0,
            ),
        },
    )

    assert incident_types(snapshot) == {"wifi_outage"}


def test_router_outage_correlates_failed_router_checks() -> None:
    snapshot = replace_measurements(
        healthy_snapshot(),
        {
            (WIRED, "router_ping"): measurement(
                WIRED,
                "wired_reference",
                "router_ping",
                "router",
                success=0,
                latency=None,
                loss=100,
            ),
            (WIFI, "router_ping"): measurement(
                WIFI,
                "wifi_observer",
                "router_ping",
                "router",
                success=0,
                latency=None,
                loss=100,
            ),
        },
    )

    assert incident_types(snapshot) == {"router_unavailable"}


def test_isp_outage_requires_healthy_router_and_both_agents_external_failure() -> None:
    snapshot = replace_measurements(
        healthy_snapshot(),
        {
            (WIRED, "external_ping"): measurement(
                WIRED,
                "wired_reference",
                "external_ping",
                "public-dns-a",
                success=0,
                latency=None,
                loss=100,
            ),
            (WIFI, "external_ping"): measurement(
                WIFI,
                "wifi_observer",
                "external_ping",
                "public-dns-a",
                success=0,
                latency=None,
                loss=100,
            ),
        },
    )

    assert incident_types(snapshot) == {"isp_outage"}


def test_dns_outage_preserves_healthy_ip_reachability() -> None:
    snapshot = healthy_snapshot()
    failed_dns = tuple(
        service(item.agent_id, item.agent_role, "dns", item.endpoint_id, success=0)
        if item.check_type == "dns"
        else item
        for item in snapshot.services
    )

    assert incident_types(
        ObservationSnapshot(AT, snapshot.measurements, failed_dns, snapshot.heartbeats)
    ) == {"dns_failure"}


def test_external_service_failure_requires_network_and_dns_health() -> None:
    snapshot = healthy_snapshot()
    failed_http = tuple(
        service(item.agent_id, item.agent_role, "http", item.endpoint_id, success=0)
        if item.check_type == "http"
        else item
        for item in snapshot.services
    )

    assert incident_types(
        ObservationSnapshot(AT, snapshot.measurements, failed_http, snapshot.heartbeats)
    ) == {"external_service_failure"}


@pytest.mark.parametrize(
    ("metric", "expected"),
    [("latency", "high_latency"), ("loss", "high_packet_loss")],
)
def test_cross_agent_anomalies_are_classified(metric: str, expected: str) -> None:
    kwargs = {"latency": 240.0} if metric == "latency" else {"loss": 35.0}
    snapshot = replace_measurements(
        healthy_snapshot(),
        {
            (WIRED, "external_ping"): measurement(
                WIRED, "wired_reference", "external_ping", "public-dns-a", **kwargs
            ),
            (WIFI, "external_ping"): measurement(
                WIFI, "wifi_observer", "external_ping", "public-dns-a", **kwargs
            ),
        },
    )

    assert incident_types(snapshot) == {expected}


def test_single_failed_ping_does_not_create_incident() -> None:
    snapshot = replace_measurements(
        healthy_snapshot(),
        {
            (WIRED, "router_ping"): measurement(
                WIRED,
                "wired_reference",
                "router_ping",
                "router",
                samples=1,
                success=0,
                latency=None,
                loss=100,
            )
        },
    )

    assert incident_types(snapshot) == set()


def test_repeated_uncorrelated_impairment_is_reported_as_unknown() -> None:
    snapshot = replace_measurements(
        healthy_snapshot(),
        {
            (WIRED, "external_ping"): measurement(
                WIRED,
                "wired_reference",
                "external_ping",
                "public-dns-a",
                success=0,
                latency=None,
                loss=100,
            )
        },
    )

    assert incident_types(snapshot) == {"unknown_network_incident"}


def test_agent_offline_requires_another_current_agent() -> None:
    snapshot = healthy_snapshot()
    heartbeats = (
        HeartbeatSummary(WIRED, "wired_reference", AT),
        HeartbeatSummary(WIFI, "wifi_observer", AT - timedelta(minutes=10)),
    )

    assert incident_types(
        ObservationSnapshot(AT, snapshot.measurements, snapshot.services, heartbeats)
    ) == {"agent_offline"}


def test_state_machine_opens_recovers_and_resolves() -> None:
    engine = ClassificationEngine(config())
    degraded = replace_measurements(
        healthy_snapshot(),
        {
            (WIFI, "router_ping"): measurement(
                WIFI, "wifi_observer", "router_ping", "router", latency=85, loss=18
            ),
            (WIFI, "wifi_diagnostics"): measurement(
                WIFI,
                "wifi_observer",
                "wifi_diagnostics",
                "wifi-interface",
                latency=None,
                signal=-84,
                connected=100,
            ),
        },
    )
    finding = engine.classify(degraded)[0]
    candidate = engine.transition(degraded, (finding,), ())[0]
    active = ActiveIncident(
        candidate.incident_id,
        finding.incident_key,
        finding.incident_type,
        candidate.start_time,
        candidate.status,
        candidate.state_revision,
        candidate.positive_observations,
        candidate.recovery_observations,
        finding,
    )
    opened = engine.transition(degraded, (finding,), (active,))[0]
    assert opened.status == "open"

    active = ActiveIncident(
        opened.incident_id,
        finding.incident_key,
        finding.incident_type,
        opened.start_time,
        opened.status,
        opened.state_revision,
        opened.positive_observations,
        opened.recovery_observations,
        finding,
    )
    recovering = engine.transition(healthy_snapshot(), (), (active,))[0]
    assert recovering.status == "recovering"

    active = ActiveIncident(
        recovering.incident_id,
        finding.incident_key,
        finding.incident_type,
        recovering.start_time,
        recovering.status,
        recovering.state_revision,
        recovering.positive_observations,
        recovering.recovery_observations,
        finding,
    )
    resolved = engine.transition(healthy_snapshot(), (), (active,))[0]
    assert resolved.status == "resolved"
    assert resolved.end_time == AT
