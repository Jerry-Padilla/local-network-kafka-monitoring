"""Kafka topic names and event routing."""

from __future__ import annotations

RAW_MEASUREMENTS_TOPIC = "network.measurements.raw.v1"
VALID_MEASUREMENTS_TOPIC = "network.measurements.valid.v1"
SERVICE_CHECKS_TOPIC = "network.service-checks.raw.v1"
SPEED_TESTS_TOPIC = "network.speed-tests.raw.v1"
HEARTBEATS_TOPIC = "network.agent-heartbeats.v1"
INCIDENTS_TOPIC = "network.incidents.v1"
DEAD_LETTER_TOPIC = "network.dead-letter.v1"
PROCESSING_METRICS_TOPIC = "network.processing-metrics.v1"

ALL_TOPICS = (
    RAW_MEASUREMENTS_TOPIC,
    VALID_MEASUREMENTS_TOPIC,
    SERVICE_CHECKS_TOPIC,
    SPEED_TESTS_TOPIC,
    HEARTBEATS_TOPIC,
    INCIDENTS_TOPIC,
    DEAD_LETTER_TOPIC,
    PROCESSING_METRICS_TOPIC,
)

RAW_INPUT_TOPICS = (
    RAW_MEASUREMENTS_TOPIC,
    SERVICE_CHECKS_TOPIC,
    SPEED_TESTS_TOPIC,
    HEARTBEATS_TOPIC,
)

_EVENT_TOPICS = {
    "network.measurement": RAW_MEASUREMENTS_TOPIC,
    "network.service_check": SERVICE_CHECKS_TOPIC,
    "network.speed_test": SPEED_TESTS_TOPIC,
    "network.agent_heartbeat": HEARTBEATS_TOPIC,
    "network.incident": INCIDENTS_TOPIC,
}


def topic_for_event(event_type: str) -> str:
    """Return the versioned topic for an event type."""
    try:
        return _EVENT_TOPICS[event_type]
    except KeyError as error:
        raise ValueError(f"unsupported event type: {event_type}") from error
