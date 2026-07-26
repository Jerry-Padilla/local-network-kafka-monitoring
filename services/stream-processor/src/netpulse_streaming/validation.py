"""Dependency-light validation shared by tests and Spark expressions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

REQUIRED_FIELDS = {
    "event_id",
    "event_type",
    "schema_version",
    "agent_id",
    "agent_role",
    "event_time",
    "published_time",
    "sequence_number",
    "source_version",
    "measurement_type",
    "target_id",
    "success",
    "packet_loss_pct",
}
MEASUREMENT_TYPES = {"router_ping", "external_ping", "wifi_diagnostics"}
AGENT_ROLES = {"wired_reference", "wifi_observer"}


def validate_measurement_mapping(payload: dict[str, object]) -> list[str]:
    """Return stable validation errors for a decoded measurement mapping."""
    errors = [f"missing:{name}" for name in sorted(REQUIRED_FIELDS - payload.keys())]
    if errors:
        return errors

    if payload["event_type"] != "network.measurement":
        errors.append("unsupported:event_type")
    if payload["schema_version"] != 1:
        errors.append("unsupported:schema_version")
    if payload["agent_role"] not in AGENT_ROLES:
        errors.append("invalid:agent_role")
    if payload["measurement_type"] not in MEASUREMENT_TYPES:
        errors.append("invalid:measurement_type")
    if not isinstance(payload["success"], bool):
        errors.append("invalid:success")

    packet_loss = payload["packet_loss_pct"]
    if not isinstance(packet_loss, int | float) or isinstance(packet_loss, bool):
        errors.append("invalid:packet_loss_pct")
    elif not 0 <= float(packet_loss) <= 100:
        errors.append("range:packet_loss_pct")

    sequence = payload["sequence_number"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        errors.append("invalid:sequence_number")

    try:
        UUID(str(payload["event_id"]))
    except (TypeError, ValueError):
        errors.append("invalid:event_id")

    for field_name in ("event_time", "published_time"):
        try:
            parsed = datetime.fromisoformat(str(payload[field_name]).replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"invalid:{field_name}")
            continue
        if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
            errors.append(f"not_utc:{field_name}")
    return errors
