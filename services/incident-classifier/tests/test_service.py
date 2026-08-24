from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from netpulse_classifier.config import ClassifierConfig
from netpulse_classifier.models import Finding, ObservationSnapshot, Transition
from netpulse_classifier.service import IncidentClassifierService
from netpulse_contracts.models import AgentRole
from netpulse_contracts.validation import validate_event


def test_incident_event_is_valid_and_uses_system_role() -> None:
    at = datetime(2026, 7, 26, 12, tzinfo=UTC)
    finding = Finding(
        "isp_outage",
        "isp_outage",
        "critical",
        0.92,
        ("network-agent-ethernet-01", "network-agent-wifi-01"),
        ("router", "public-dns-a"),
        ({"rule": "router_healthy_external_failed"},),
        None,
        100,
        "Both agents cannot reach external targets.",
        "Inspect modem and WAN status.",
    )
    transition = Transition(uuid4(), finding, at, None, "open", 2, 2, 0)

    event = IncidentClassifierService._event(transition, at)
    validated = validate_event(json.dumps(event.model_dump(mode="json")))

    assert validated.agent_role is AgentRole.SYSTEM_CLASSIFIER
    assert validated.status == "open"
    assert validated.correlation_id == transition.incident_id


class FakeRepository:
    def __init__(self, transition: Transition) -> None:
        self._transition = transition
        self.pending: list[tuple[UUID, UUID, bytes]] = [
            (uuid4(), transition.incident_id, b'{"previous":true}')
        ]
        self.persisted = []
        self.marked: list[UUID] = []

    def load_snapshot(self, observed_at: datetime, _lookback: int) -> ObservationSnapshot:
        return ObservationSnapshot(observed_at, (), (), ())

    def load_active(self) -> tuple[object, ...]:
        return ()

    def persist_transition(self, transition: Transition, event: object) -> None:
        self.persisted.append((transition, event))
        incident = event
        payload = json.dumps(incident.model_dump(mode="json")).encode()
        self.pending.append((incident.event_id, transition.incident_id, payload))

    def pending_publications(self) -> tuple[tuple[UUID, UUID, bytes], ...]:
        return tuple(self.pending)

    def mark_published(self, event_id: UUID) -> None:
        self.marked.append(event_id)
        self.pending = [item for item in self.pending if item[0] != event_id]


class FakePublisher:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, bytes]] = []

    def publish(self, topic: str, key: str, value: bytes) -> None:
        self.records.append((topic, key, value))


class FakeEngine:
    def __init__(self, finding: Finding, transition: Transition) -> None:
        self._finding = finding
        self._transition = transition

    def classify(self, _snapshot: ObservationSnapshot) -> tuple[Finding, ...]:
        return (self._finding,)

    def transition(
        self,
        _snapshot: ObservationSnapshot,
        _findings: tuple[Finding, ...],
        _active: tuple[object, ...],
    ) -> tuple[Transition, ...]:
        return (self._transition,)


def test_cycle_flushes_old_outbox_before_persisting_and_publishing_transition() -> None:
    at = datetime(2026, 7, 26, 12, tzinfo=UTC)
    finding = Finding(
        "dns_failure:dns-check",
        "dns_failure",
        "critical",
        0.9,
        ("network-agent-ethernet-01", "network-agent-wifi-01"),
        ("dns-check",),
        ({"rule": "dns_failed_ip_healthy"},),
        None,
        None,
        "DNS failed while IP checks remained healthy.",
        "Inspect configured resolvers.",
    )
    transition = Transition(uuid4(), finding, at, None, "candidate", 1, 1, 0)
    repository = FakeRepository(transition)
    publisher = FakePublisher()
    config = ClassifierConfig(
        "broker:9092",
        "postgresql://unused",
        "test",
        60,
        10,
        2,
        2,
        2,
        80,
        20,
        150,
        20,
        -78,
        150,
        1,
    )
    service = IncidentClassifierService(
        config,
        repository,  # type: ignore[arg-type]
        publisher,  # type: ignore[arg-type]
        FakeEngine(finding, transition),  # type: ignore[arg-type]
    )

    count = service.evaluate_once(at)

    assert count == 1
    assert len(repository.persisted) == 1
    assert len(repository.marked) == 2
    assert len(publisher.records) == 2
    assert repository.pending == []
