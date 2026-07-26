from __future__ import annotations

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.config import PrivacyConfig
from netpulse_agent.events import EventFactory
from netpulse_agent.privacy import protect_identifier, protect_wifi_identifiers
from netpulse_contracts.models import NetworkMeasurement


def test_privacy_modes_are_explicit_and_deterministic() -> None:
    assert protect_identifier("home", "omit", "12345678") is None
    assert protect_identifier("home", "plain", "12345678") == "home"
    first = protect_identifier("home", "hash", "12345678")
    second = protect_identifier("home", "hash", "12345678")
    assert first == second
    assert first is not None and first.startswith("sha256:")

    assert protect_wifi_identifiers(
        "ssid",
        "aa:bb:cc:dd:ee:ff",
        PrivacyConfig(ssid="hash", bssid="omit", hash_salt="12345678"),
    ) == (protect_identifier("ssid", "hash", "12345678"), None)


def test_event_factory_validates_additive_collector_fields(
    event_factory: EventFactory,
) -> None:
    event = event_factory.build(
        CollectedEvent(
            "network.measurement",
            {
                "measurement_type": "wifi_diagnostics",
                "target_id": "wlan0",
                "success": True,
                "packet_loss_pct": 0,
                "connected": True,
                "signal_dbm": -55,
                "frequency_mhz": 2_437,
            },
        )
    )

    assert isinstance(event, NetworkMeasurement)
    assert event.sequence_number == 0
    assert event.model_dump()["frequency_mhz"] == 2_437
