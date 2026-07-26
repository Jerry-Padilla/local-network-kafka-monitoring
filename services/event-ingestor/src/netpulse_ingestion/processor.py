"""One-record ingestion workflow independent of Kafka polling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from netpulse_contracts.models import Event, NetworkMeasurement
from netpulse_contracts.topics import DEAD_LETTER_TOPIC, VALID_MEASUREMENTS_TOPIC
from netpulse_contracts.validation import EventValidationError, validate_event

from netpulse_ingestion.processor_types import SourceRecord

KNOWN_AGENTS = {
    "network-agent-ethernet-01",
    "network-agent-wifi-01",
}
KNOWN_ENDPOINTS = {
    "router",
    "public-dns-a",
    "public-dns-b",
    "wifi-interface",
    "dns-check",
    "example-service",
}


class EventRepository(Protocol):
    def persist_event(self, event: Event, source: SourceRecord) -> None: ...

    def record_failure(
        self,
        source: SourceRecord,
        error_class: str,
        error_message: str,
        validation_errors: list[dict[str, Any]],
    ) -> None: ...

    def mark_dead_letter_published(self, source: SourceRecord) -> None: ...


class OutputPublisher(Protocol):
    def publish(self, topic: str, key: str | None, value: bytes) -> None: ...


class ProcessingOutcome(StrEnum):
    VALID = "valid"
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    outcome: ProcessingOutcome
    event_id: str | None


class EventProcessor:
    """Validate, persist, and route one source record."""

    def __init__(
        self,
        repository: EventRepository,
        publisher: OutputPublisher,
        known_agents: set[str] | None = None,
        known_endpoints: set[str] | None = None,
    ) -> None:
        self._repository = repository
        self._publisher = publisher
        self._known_agents = known_agents or KNOWN_AGENTS
        self._known_endpoints = known_endpoints or KNOWN_ENDPOINTS

    def process(self, source: SourceRecord) -> ProcessingResult:
        try:
            event = validate_event(source.value)
            self._validate_references(event)
        except EventValidationError as error:
            self._dead_letter(source, error)
            return ProcessingResult(ProcessingOutcome.DEAD_LETTERED, None)

        self._repository.persist_event(event, source)
        if isinstance(event, NetworkMeasurement):
            value = json.dumps(
                event.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
            ).encode()
            self._publisher.publish(
                VALID_MEASUREMENTS_TOPIC,
                event.agent_id,
                value,
            )
        return ProcessingResult(ProcessingOutcome.VALID, str(event.event_id))

    def _validate_references(self, event: Event) -> None:
        if event.agent_id not in self._known_agents:
            raise EventValidationError(f"unrecognized agent_id: {event.agent_id}")
        endpoint = getattr(event, "target_id", None) or getattr(event, "endpoint_id", None)
        if endpoint is not None and endpoint not in self._known_endpoints:
            raise EventValidationError(f"unrecognized endpoint: {endpoint}")

    def _dead_letter(self, source: SourceRecord, error: EventValidationError) -> None:
        self._repository.record_failure(
            source,
            type(error).__name__,
            str(error),
            error.errors,
        )
        dead_letter = {
            "dead_letter_id": str(uuid4()),
            "failed_time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source_topic": source.topic,
            "source_partition": source.partition,
            "source_offset": source.offset,
            "error_class": type(error).__name__,
            "error_message": str(error),
            "validation_errors": error.errors,
            "original_payload": source.value.decode("utf-8", errors="replace"),
        }
        self._publisher.publish(
            DEAD_LETTER_TOPIC,
            source.key,
            json.dumps(dead_letter, separators=(",", ":"), sort_keys=True).encode(),
        )
        self._repository.mark_dead_letter_published(source)
