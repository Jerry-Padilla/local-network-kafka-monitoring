import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from netpulse_contracts.models import NetworkMeasurement
from netpulse_contracts.validation import EventValidationError, validate_event


def measurement_payload() -> dict[str, object]:
    timestamp = datetime(2026, 7, 25, 12, tzinfo=UTC).isoformat()
    return {
        "event_id": "16a29c74-0880-4f22-bec3-d8cc84d3e420",
        "event_type": "network.measurement",
        "schema_version": 1,
        "agent_id": "network-agent-wifi-01",
        "agent_role": "wifi_observer",
        "event_time": timestamp,
        "published_time": timestamp,
        "sequence_number": 7,
        "correlation_id": None,
        "source_version": "0.1.0",
        "measurement_type": "external_ping",
        "target_id": "public-dns-a",
        "success": True,
        "latency_ms": 25.5,
        "packet_loss_pct": 0,
    }


def test_additive_fields_are_preserved() -> None:
    payload = measurement_payload()
    payload["future_optional_metric"] = 123

    event = validate_event(payload)

    assert isinstance(event, NetworkMeasurement)
    assert event.model_dump()["future_optional_metric"] == 123


def test_high_latency_and_loss_are_valid_not_contract_errors() -> None:
    payload = measurement_payload()
    payload["latency_ms"] = 5_000
    payload["packet_loss_pct"] = 99.9

    event = validate_event(json.dumps(payload))

    assert isinstance(event, NetworkMeasurement)
    assert event.latency_ms == 5_000
    assert event.packet_loss_pct == 99.9


@pytest.mark.parametrize("packet_loss", [-0.1, 100.1])
def test_packet_loss_outside_percentage_range_is_rejected(packet_loss: float) -> None:
    payload = measurement_payload()
    payload["packet_loss_pct"] = packet_loss

    with pytest.raises(EventValidationError):
        validate_event(payload)


def test_unknown_schema_version_is_rejected() -> None:
    payload = measurement_payload()
    payload["schema_version"] = 2

    with pytest.raises(EventValidationError):
        validate_event(payload)


def test_non_utc_timestamp_is_rejected() -> None:
    payload = measurement_payload()
    non_utc = datetime(2026, 7, 25, 12, tzinfo=timezone(timedelta(hours=-7)))
    payload["event_time"] = non_utc.isoformat()

    with pytest.raises(EventValidationError):
        validate_event(payload)


def test_malformed_json_has_specific_validation_failure() -> None:
    with pytest.raises(EventValidationError, match="invalid UTF-8 JSON"):
        validate_event(b'{"broken":')
