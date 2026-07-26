from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from netpulse_streaming.validation import validate_measurement_mapping


def valid_payload() -> dict[str, object]:
    now = datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    return {
        "event_id": str(uuid4()),
        "event_type": "network.measurement",
        "schema_version": 1,
        "agent_id": "network-agent-wifi-01",
        "agent_role": "wifi_observer",
        "event_time": now,
        "published_time": now,
        "sequence_number": 1,
        "source_version": "0.2.0",
        "measurement_type": "external_ping",
        "target_id": "public-dns-a",
        "success": True,
        "packet_loss_pct": 0.0,
        "additive_future_field": {"supported": True},
    }


def test_valid_measurement_allows_additive_fields_and_anomalies() -> None:
    payload = valid_payload()
    payload["latency_ms"] = 9_999.0
    payload["packet_loss_pct"] = 95.0

    assert validate_measurement_mapping(payload) == []


def test_invalid_measurement_reports_stable_errors() -> None:
    payload = valid_payload()
    payload["event_id"] = "not-a-uuid"
    payload["schema_version"] = 99
    payload["packet_loss_pct"] = 101.0

    assert validate_measurement_mapping(payload) == [
        "unsupported:schema_version",
        "range:packet_loss_pct",
        "invalid:event_id",
    ]


def test_missing_required_fields_are_reported_without_key_errors() -> None:
    assert validate_measurement_mapping({"event_type": "network.measurement"}) == [
        "missing:agent_id",
        "missing:agent_role",
        "missing:event_id",
        "missing:event_time",
        "missing:measurement_type",
        "missing:packet_loss_pct",
        "missing:published_time",
        "missing:schema_version",
        "missing:sequence_number",
        "missing:source_version",
        "missing:success",
        "missing:target_id",
    ]
