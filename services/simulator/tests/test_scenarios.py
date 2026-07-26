import json
from datetime import UTC, datetime

import pytest
from netpulse_contracts.validation import EventValidationError, validate_event
from netpulse_simulator.scenarios import (
    SCENARIOS,
    WIFI_AGENT_ID,
    WIRED_AGENT_ID,
    ScenarioGenerator,
)

FIXED_TIME = datetime(2026, 7, 25, 12, tzinfo=UTC)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_named_scenario_generates_records(scenario: str) -> None:
    records = ScenarioGenerator(seed=7).generate_round(scenario, FIXED_TIME)

    assert records
    if scenario == "malformed-events":
        invalid = 0
        for record in records:
            try:
                validate_event(record.value)
            except EventValidationError:
                invalid += 1
        assert invalid == 1
    else:
        assert all(validate_event(record.value) for record in records)


def test_fixed_seed_and_time_are_byte_deterministic() -> None:
    first = ScenarioGenerator(seed=88).generate_round("healthy", FIXED_TIME)
    second = ScenarioGenerator(seed=88).generate_round("healthy", FIXED_TIME)

    assert first == second


def test_duplicate_scenario_reuses_identical_event_id() -> None:
    records = ScenarioGenerator(seed=2).generate_round("duplicate-events", FIXED_TIME)

    assert records[0] == records[-1]
    assert json.loads(records[0].value)["event_id"] == json.loads(records[-1].value)["event_id"]


def test_agent_shutdown_omits_wireless_agent() -> None:
    records = ScenarioGenerator(seed=2).generate_round("agent-shutdown", FIXED_TIME)
    agent_ids = {json.loads(record.value)["agent_id"] for record in records}

    assert WIRED_AGENT_ID in agent_ids
    assert WIFI_AGENT_ID not in agent_ids


def test_wifi_degradation_preserves_healthy_wired_baseline() -> None:
    records = ScenarioGenerator(seed=2).generate_round("wifi-degradation", FIXED_TIME)
    events = [json.loads(record.value) for record in records]
    wired_external = next(
        event
        for event in events
        if event["agent_id"] == WIRED_AGENT_ID and event.get("measurement_type") == "external_ping"
    )
    wifi_external = next(
        event
        for event in events
        if event["agent_id"] == WIFI_AGENT_ID and event.get("measurement_type") == "external_ping"
    )

    assert wired_external["success"] is True
    assert wifi_external["latency_ms"] > wired_external["latency_ms"]
    assert wifi_external["packet_loss_pct"] > wired_external["packet_loss_pct"]
