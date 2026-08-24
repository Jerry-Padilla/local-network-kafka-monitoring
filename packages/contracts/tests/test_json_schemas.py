from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from netpulse_classifier.models import Finding, Transition
from netpulse_classifier.service import IncidentClassifierService
from netpulse_simulator.scenarios import ScenarioGenerator
from referencing import Registry, Resource

SCHEMA_ROOT = Path(__file__).parents[3] / "schemas"


def _schemas() -> dict[str, dict[str, object]]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_ROOT.glob("*.schema.json")
    }


def test_all_schema_documents_are_valid_draft_2020_12() -> None:
    for schema in _schemas().values():
        Draft202012Validator.check_schema(schema)


def test_simulator_events_conform_to_published_json_schemas() -> None:
    schemas = _schemas()
    resources = [
        (str(schema["$id"]), Resource.from_contents(schema)) for schema in schemas.values()
    ]
    registry = Registry().with_resources(resources)
    validators = {
        "network.measurement": Draft202012Validator(
            schemas["network_measurement.schema.json"],
            registry=registry,
            format_checker=FormatChecker(),
        ),
        "network.service_check": Draft202012Validator(
            schemas["service_check.schema.json"],
            registry=registry,
            format_checker=FormatChecker(),
        ),
        "network.agent_heartbeat": Draft202012Validator(
            schemas["agent_heartbeat.schema.json"],
            registry=registry,
            format_checker=FormatChecker(),
        ),
    }
    records = ScenarioGenerator(seed=4).generate_round(
        "healthy",
        at=__import__("datetime").datetime(2026, 7, 25, tzinfo=__import__("datetime").UTC),
    )

    for record in records:
        payload = json.loads(record.value)
        validator = validators[payload["event_type"]]
        assert list(validator.iter_errors(payload)) == []


def test_additive_payload_field_is_schema_compatible() -> None:
    schemas = _schemas()
    resources = [
        (str(schema["$id"]), Resource.from_contents(schema)) for schema in schemas.values()
    ]
    registry = Registry().with_resources(resources)
    validator = Draft202012Validator(
        schemas["network_measurement.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )
    record = ScenarioGenerator(seed=1).generate_round(
        "healthy",
        at=__import__("datetime").datetime(2026, 7, 25, tzinfo=__import__("datetime").UTC),
    )[0]
    payload = json.loads(record.value)
    payload["future_optional_metric"] = "accepted"

    assert list(validator.iter_errors(payload)) == []


def test_classifier_incident_conforms_to_published_json_schema() -> None:
    schemas = _schemas()
    resources = [
        (str(schema["$id"]), Resource.from_contents(schema)) for schema in schemas.values()
    ]
    registry = Registry().with_resources(resources)
    validator = Draft202012Validator(
        schemas["network_incident.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )
    at = datetime(2026, 7, 26, 12, tzinfo=UTC)
    finding = Finding(
        "isp_outage",
        "isp_outage",
        "critical",
        0.92,
        ("network-agent-ethernet-01", "network-agent-wifi-01"),
        ("public-dns-a",),
        ({"rule": "router_healthy_external_failed"},),
        None,
        100,
        "Both agents repeatedly failed external checks.",
        "Inspect modem and WAN status.",
    )
    transition = Transition(uuid4(), finding, at, None, "open", 2, 2, 0)
    event = IncidentClassifierService._event(transition, at)

    assert list(validator.iter_errors(event.model_dump(mode="json"))) == []
