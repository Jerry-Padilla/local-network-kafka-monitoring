"""Shared NetPulse event contracts."""

from netpulse_contracts.models import (
    AgentHeartbeat,
    AgentRole,
    Event,
    Incident,
    NetworkMeasurement,
    ServiceCheck,
    SpeedTest,
)
from netpulse_contracts.topics import DEAD_LETTER_TOPIC, topic_for_event
from netpulse_contracts.validation import EventValidationError, validate_event

__all__ = [
    "DEAD_LETTER_TOPIC",
    "AgentHeartbeat",
    "AgentRole",
    "Event",
    "EventValidationError",
    "Incident",
    "NetworkMeasurement",
    "ServiceCheck",
    "SpeedTest",
    "topic_for_event",
    "validate_event",
]
