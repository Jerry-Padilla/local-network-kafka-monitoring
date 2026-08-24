"""Deterministic cross-agent rules and incident lifecycle transitions."""

from __future__ import annotations

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from netpulse_classifier.config import ClassifierConfig
from netpulse_classifier.models import (
    ActiveIncident,
    Finding,
    IncidentStatus,
    MeasurementSummary,
    ObservationSnapshot,
    ServiceSummary,
    Transition,
)

WIRED_ROLE = "wired_reference"
WIFI_ROLE = "wifi_observer"


class ClassificationEngine:
    """Classify symptoms without claiming access to infrastructure root cause."""

    def __init__(self, config: ClassifierConfig) -> None:
        self._config = config

    def classify(self, snapshot: ObservationSnapshot) -> tuple[Finding, ...]:
        measurements = tuple(
            item
            for item in snapshot.measurements
            if item.sample_count >= self._config.minimum_samples
        )
        services = tuple(
            item for item in snapshot.services if item.sample_count >= self._config.minimum_samples
        )
        findings: list[Finding] = []

        wired_router = self._measurements(measurements, WIRED_ROLE, "router_ping")
        wifi_router = self._measurements(measurements, WIFI_ROLE, "router_ping")
        wired_external = self._measurements(measurements, WIRED_ROLE, "external_ping")
        wifi_external = self._measurements(measurements, WIFI_ROLE, "external_ping")
        wifi_diagnostics = self._measurements(measurements, WIFI_ROLE, "wifi_diagnostics")
        all_router = wired_router + wifi_router
        all_external = wired_external + wifi_external

        wired_router_healthy = self._all_healthy(wired_router)
        wifi_router_healthy = self._all_healthy(wifi_router)
        routers_healthy = wired_router_healthy and wifi_router_healthy
        wired_external_healthy = self._all_healthy(wired_external)
        wifi_external_healthy = self._all_healthy(wifi_external)
        external_healthy = wired_external_healthy and wifi_external_healthy

        if self._all_failed(wired_router) and self._all_failed(wifi_router):
            findings.append(
                self._finding(
                    "router_unavailable",
                    "critical",
                    0.94,
                    all_router,
                    "Both agents repeatedly failed to reach the configured router.",
                    "Check router power, local cabling, and LAN interface status.",
                )
            )
        elif (
            wired_router_healthy
            and wired_external_healthy
            and self._all_failed(wifi_router)
            and self._wifi_disconnected(wifi_diagnostics)
        ):
            findings.append(
                self._finding(
                    "wifi_outage",
                    "critical",
                    0.96,
                    wifi_router + wifi_diagnostics,
                    "The wired baseline is healthy while the Wi-Fi agent cannot reach "
                    "the router and reports no association.",
                    "Check the access point, Wi-Fi credentials, channel, and agent location.",
                )
            )
        elif (
            routers_healthy and self._all_failed(wired_external) and self._all_failed(wifi_external)
        ):
            findings.append(
                self._finding(
                    "isp_outage",
                    "critical",
                    0.92,
                    all_router + all_external,
                    "Both agents can reach the router but repeatedly fail external IP checks.",
                    "Check modem or WAN status, then contact the ISP if the condition persists.",
                )
            )
        elif (
            wired_router_healthy
            and wired_external_healthy
            and wifi_router
            and self._wifi_degraded(wifi_router + wifi_external, wifi_diagnostics)
        ):
            findings.append(
                self._finding(
                    "wifi_degradation",
                    "warning",
                    0.88,
                    wifi_router + wifi_external + wifi_diagnostics,
                    "The wired baseline is healthy while Wi-Fi latency, loss, or signal "
                    "quality is degraded.",
                    "Move the Wi-Fi agent or access point, then inspect interference and "
                    "channel utilization.",
                )
            )
        elif routers_healthy and external_healthy:
            dns = self._services(services, "dns")
            http = self._services(services, "http")
            if self._cross_agent_failed(dns):
                findings.append(
                    self._service_finding(
                        "dns_failure",
                        "critical",
                        0.9,
                        dns,
                        "IP reachability is healthy while DNS checks repeatedly fail across "
                        "both agents.",
                        "Test an alternate configured resolver and inspect router DNS settings.",
                    )
                )
            elif self._all_healthy_services(dns):
                failing_http = tuple(
                    item
                    for item in http
                    if item.success_rate_pct <= self._config.failed_success_rate_pct
                )
                healthy_http = tuple(
                    item
                    for item in http
                    if item.success_rate_pct >= self._config.healthy_success_rate_pct
                )
                if failing_http and (healthy_http or len({i.endpoint_id for i in http}) == 1):
                    findings.append(
                        self._service_finding(
                            "external_service_failure",
                            "warning",
                            0.84,
                            failing_http,
                            "Network and DNS checks are healthy while a configured external "
                            "service repeatedly fails.",
                            "Check the service status and test the endpoint from another network.",
                        )
                    )

        if not findings:
            high_loss = tuple(
                item
                for item in measurements
                if item.measurement_type != "wifi_diagnostics"
                and item.mean_packet_loss_pct >= self._config.high_packet_loss_pct
            )
            high_latency = tuple(
                item
                for item in measurements
                if item.peak_latency_ms is not None
                and item.peak_latency_ms >= self._config.high_latency_ms
            )
            if self._covers_both_agents(high_loss):
                findings.append(
                    self._finding(
                        "high_packet_loss",
                        "warning",
                        0.82,
                        high_loss,
                        "Repeated high packet loss is present across wired and Wi-Fi agents.",
                        "Inspect router load and WAN quality; compare local and external targets.",
                    )
                )
            elif self._covers_both_agents(high_latency):
                findings.append(
                    self._finding(
                        "high_latency",
                        "warning",
                        0.8,
                        high_latency,
                        "Repeated high latency is present across wired and Wi-Fi agents.",
                        "Check local congestion and compare router latency with external latency.",
                    )
                )
            else:
                unexplained = tuple(
                    item
                    for item in measurements
                    if item.measurement_type != "wifi_diagnostics"
                    and (
                        item.success_rate_pct <= self._config.failed_success_rate_pct
                        or item.mean_packet_loss_pct >= self._config.high_packet_loss_pct
                        or (
                            item.peak_latency_ms is not None
                            and item.peak_latency_ms >= self._config.high_latency_ms
                        )
                    )
                )
                if unexplained:
                    findings.append(
                        self._finding(
                            "unknown_network_incident",
                            "warning",
                            0.5,
                            unexplained,
                            "Repeated impairment is present, but the available cross-agent "
                            "evidence does not support a more specific classification.",
                            "Inspect the affected target and compare both agents before "
                            "escalating.",
                        )
                    )

        findings.extend(self._offline_findings(snapshot))
        return tuple(findings)

    def transition(
        self,
        snapshot: ObservationSnapshot,
        findings: tuple[Finding, ...],
        active: tuple[ActiveIncident, ...],
    ) -> tuple[Transition, ...]:
        """Advance each finding through candidate/open/recovery/resolved states."""
        active_by_key = {item.incident_key: item for item in active}
        finding_by_key = {item.incident_key: item for item in findings}
        transitions: list[Transition] = []

        for key, finding in finding_by_key.items():
            previous = active_by_key.get(key)
            if previous is None:
                incident_id = uuid5(
                    NAMESPACE_URL,
                    f"netpulse-incident:{key}:{snapshot.observed_at.isoformat()}",
                )
                transitions.append(
                    Transition(
                        incident_id=incident_id,
                        finding=finding,
                        start_time=snapshot.observed_at,
                        end_time=None,
                        status="candidate",
                        state_revision=1,
                        positive_observations=1,
                        recovery_observations=0,
                    )
                )
                continue

            positives = previous.positive_observations + 1
            status: IncidentStatus
            if previous.status == "candidate":
                status = "open" if positives >= self._config.open_observations else "candidate"
            elif previous.status == "recovering":
                status = "open"
            else:
                status = "ongoing"
            transitions.append(
                Transition(
                    incident_id=previous.incident_id,
                    finding=finding,
                    start_time=previous.start_time,
                    end_time=None,
                    status=status,
                    state_revision=previous.state_revision + 1,
                    positive_observations=positives,
                    recovery_observations=0,
                )
            )

        for key, previous in active_by_key.items():
            if key in finding_by_key:
                continue
            recoveries = previous.recovery_observations + 1
            resolved = previous.status == "candidate" or (
                previous.status == "recovering" and recoveries >= self._config.resolve_observations
            )
            transitions.append(
                Transition(
                    incident_id=previous.incident_id,
                    finding=previous.finding,
                    start_time=previous.start_time,
                    end_time=snapshot.observed_at if resolved else None,
                    status="resolved" if resolved else "recovering",
                    state_revision=previous.state_revision + 1,
                    positive_observations=previous.positive_observations,
                    recovery_observations=recoveries,
                )
            )
        return tuple(transitions)

    def _offline_findings(self, snapshot: ObservationSnapshot) -> list[Finding]:
        recent = {
            item.agent_id
            for item in snapshot.heartbeats
            if item.last_event_time is not None
            and snapshot.observed_at - item.last_event_time
            <= timedelta(seconds=self._config.heartbeat_stale_seconds)
        }
        if not recent:
            return []
        findings: list[Finding] = []
        for heartbeat in snapshot.heartbeats:
            if heartbeat.agent_id in recent or not recent - {heartbeat.agent_id}:
                continue
            age = (
                None
                if heartbeat.last_event_time is None
                else (snapshot.observed_at - heartbeat.last_event_time).total_seconds()
            )
            evidence: dict[str, object] = {
                "agent_id": heartbeat.agent_id,
                "last_heartbeat": (
                    heartbeat.last_event_time.isoformat()
                    if heartbeat.last_event_time is not None
                    else None
                ),
                "age_seconds": age,
                "other_recent_agents": sorted(recent),
            }
            findings.append(
                Finding(
                    incident_key=f"agent_offline:{heartbeat.agent_id}",
                    incident_type="agent_offline",
                    severity="warning",
                    confidence_score=0.86,
                    affected_agents=(heartbeat.agent_id,),
                    affected_endpoints=(),
                    evidence=(evidence,),
                    peak_latency_ms=None,
                    maximum_packet_loss_pct=None,
                    summary=(
                        f"Agent {heartbeat.agent_id} stopped reporting while another agent "
                        "remained current."
                    ),
                    recommended_action="Check agent power, network association, and service logs.",
                )
            )
        return findings

    def _finding(
        self,
        incident_type: str,
        severity: str,
        confidence: float,
        rows: tuple[MeasurementSummary, ...],
        summary: str,
        action: str,
    ) -> Finding:
        evidence = tuple(
            {
                "agent_id": row.agent_id,
                "agent_role": row.agent_role,
                "target_id": row.target_id,
                "measurement_type": row.measurement_type,
                "sample_count": row.sample_count,
                "success_rate_pct": row.success_rate_pct,
                "peak_latency_ms": row.peak_latency_ms,
                "mean_packet_loss_pct": row.mean_packet_loss_pct,
                "weakest_signal_dbm": row.weakest_signal_dbm,
                "connected_rate_pct": row.connected_rate_pct,
            }
            for row in rows
        )
        return Finding(
            incident_key=str(incident_type),
            incident_type=incident_type,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            confidence_score=confidence,
            affected_agents=tuple(sorted({row.agent_id for row in rows})),
            affected_endpoints=tuple(sorted({row.target_id for row in rows})),
            evidence=evidence,
            peak_latency_ms=max(
                (row.peak_latency_ms for row in rows if row.peak_latency_ms is not None),
                default=None,
            ),
            maximum_packet_loss_pct=max(
                (row.mean_packet_loss_pct for row in rows),
                default=None,
            ),
            summary=summary,
            recommended_action=action,
        )

    @staticmethod
    def _service_finding(
        incident_type: str,
        severity: str,
        confidence: float,
        rows: tuple[ServiceSummary, ...],
        summary: str,
        action: str,
    ) -> Finding:
        return Finding(
            incident_key=f"{incident_type}:{','.join(sorted({r.endpoint_id for r in rows}))}",
            incident_type=incident_type,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            confidence_score=confidence,
            affected_agents=tuple(sorted({row.agent_id for row in rows})),
            affected_endpoints=tuple(sorted({row.endpoint_id for row in rows})),
            evidence=tuple(
                {
                    "agent_id": row.agent_id,
                    "agent_role": row.agent_role,
                    "endpoint_id": row.endpoint_id,
                    "check_type": row.check_type,
                    "sample_count": row.sample_count,
                    "success_rate_pct": row.success_rate_pct,
                }
                for row in rows
            ),
            peak_latency_ms=None,
            maximum_packet_loss_pct=None,
            summary=summary,
            recommended_action=action,
        )

    @staticmethod
    def _measurements(
        rows: tuple[MeasurementSummary, ...], role: str, measurement_type: str
    ) -> tuple[MeasurementSummary, ...]:
        return tuple(
            item
            for item in rows
            if item.agent_role == role and item.measurement_type == measurement_type
        )

    @staticmethod
    def _services(rows: tuple[ServiceSummary, ...], check_type: str) -> tuple[ServiceSummary, ...]:
        return tuple(item for item in rows if item.check_type == check_type)

    def _all_healthy(self, rows: tuple[MeasurementSummary, ...]) -> bool:
        return bool(rows) and all(
            row.success_rate_pct >= self._config.healthy_success_rate_pct for row in rows
        )

    def _all_failed(self, rows: tuple[MeasurementSummary, ...]) -> bool:
        return bool(rows) and all(
            row.success_rate_pct <= self._config.failed_success_rate_pct for row in rows
        )

    def _all_healthy_services(self, rows: tuple[ServiceSummary, ...]) -> bool:
        return bool(rows) and all(
            row.success_rate_pct >= self._config.healthy_success_rate_pct for row in rows
        )

    def _cross_agent_failed(self, rows: tuple[ServiceSummary, ...]) -> bool:
        failing = tuple(
            item for item in rows if item.success_rate_pct <= self._config.failed_success_rate_pct
        )
        return self._covers_both_agents(failing)

    @staticmethod
    def _covers_both_agents(rows: tuple[MeasurementSummary | ServiceSummary, ...]) -> bool:
        roles = {item.agent_role for item in rows}
        return WIRED_ROLE in roles and WIFI_ROLE in roles

    def _wifi_degraded(
        self,
        network: tuple[MeasurementSummary, ...],
        diagnostics: tuple[MeasurementSummary, ...],
    ) -> bool:
        degraded_network = any(
            (
                item.peak_latency_ms is not None
                and item.peak_latency_ms >= self._config.high_latency_ms * 0.5
            )
            or item.mean_packet_loss_pct >= self._config.high_packet_loss_pct * 0.75
            for item in network
        )
        weak_signal = any(
            item.weakest_signal_dbm is not None
            and item.weakest_signal_dbm <= self._config.weak_signal_dbm
            for item in diagnostics
        )
        return degraded_network and weak_signal

    def _wifi_disconnected(self, rows: tuple[MeasurementSummary, ...]) -> bool:
        return bool(rows) and all(
            item.connected_rate_pct is not None
            and item.connected_rate_pct <= self._config.failed_success_rate_pct
            for item in rows
        )
