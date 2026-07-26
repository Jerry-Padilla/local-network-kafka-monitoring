import pytest
from netpulse_contracts.topics import (
    RAW_MEASUREMENTS_TOPIC,
    SERVICE_CHECKS_TOPIC,
    topic_for_event,
)


def test_event_types_route_to_versioned_topics() -> None:
    assert topic_for_event("network.measurement") == RAW_MEASUREMENTS_TOPIC
    assert topic_for_event("network.service_check") == SERVICE_CHECKS_TOPIC


def test_unknown_event_type_has_no_implicit_topic() -> None:
    with pytest.raises(ValueError, match="unsupported event type"):
        topic_for_event("network.unknown")
