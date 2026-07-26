from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
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
