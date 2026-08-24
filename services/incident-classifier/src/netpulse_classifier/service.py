"""Orchestrate observation, durable state changes, and Kafka publication."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

import structlog
from netpulse_contracts.models import AgentRole, Incident
from netpulse_contracts.topics import INCIDENTS_TOPIC

from netpulse_classifier.config import ClassifierConfig
from netpulse_classifier.engine import ClassificationEngine
from netpulse_classifier.publisher import IncidentPublisher
from netpulse_classifier.repository import PostgresIncidentRepository, utc_now

CLASSIFIER_ID = "netpulse-classifier-01"
RULE_VERSION = "1.0.0"


class IncidentClassifierService:
    def __init__(
        self,
        config: ClassifierConfig,
        repository: PostgresIncidentRepository,
        publisher: IncidentPublisher,
        engine: ClassificationEngine,
    ) -> None:
        self._config = config
        self._repository = repository
        self._publisher = publisher
        self._engine = engine
        self._logger = structlog.get_logger(__name__)

    def evaluate_once(self, observed_at: datetime | None = None) -> int:
        self.publish_pending()
        at = observed_at or utc_now()
        snapshot = self._repository.load_snapshot(at, self._config.lookback_seconds)
        findings = self._engine.classify(snapshot)
        active = self._repository.load_active()
        transitions = self._engine.transition(snapshot, findings, active)
        for transition in transitions:
            event = self._event(transition, at)
            self._repository.persist_transition(transition, event)
        published = self.publish_pending()
        self._logger.info(
            "classification_cycle_completed",
            findings=len(findings),
            transitions=len(transitions),
            publications=published,
            observed_at=at.isoformat(),
        )
        return len(transitions)

    def publish_pending(self) -> int:
        published = 0
        while True:
            pending = self._repository.pending_publications()
            if not pending:
                return published
            for event_id, incident_id, payload in pending:
                self._publisher.publish(INCIDENTS_TOPIC, str(incident_id), payload)
                self._repository.mark_published(event_id)
                published += 1

    @staticmethod
    def _event(transition: object, observed_at: datetime) -> Incident:
        from netpulse_classifier.models import Transition

        if not isinstance(transition, Transition):
            raise TypeError("expected Transition")
        finding = transition.finding
        duration_ms = max(0.0, (observed_at - transition.start_time).total_seconds() * 1_000)
        event_id = uuid5(
            NAMESPACE_URL,
            f"netpulse-incident-state:{transition.incident_id}:{transition.state_revision}",
        )
        return Incident(
            event_id=event_id,
            event_type="network.incident",
            schema_version=1,
            agent_id=CLASSIFIER_ID,
            agent_role=AgentRole.SYSTEM_CLASSIFIER,
            event_time=observed_at,
            published_time=observed_at,
            sequence_number=transition.state_revision,
            correlation_id=transition.incident_id,
            source_version=RULE_VERSION,
            incident_id=transition.incident_id,
            incident_type=finding.incident_type,
            start_time=transition.start_time,
            end_time=transition.end_time,
            status=transition.status,
            severity=finding.severity,
            confidence_score=finding.confidence_score,
            affected_agents=list(finding.affected_agents),
            affected_endpoints=list(finding.affected_endpoints),
            evidence=list(finding.evidence),
            rule_version=RULE_VERSION,
            peak_latency_ms=finding.peak_latency_ms,
            maximum_packet_loss_pct=finding.maximum_packet_loss_pct,
            duration_ms=duration_ms,
            summary=f"Probable classification: {finding.summary}",
            recommended_action=finding.recommended_action,
        )
