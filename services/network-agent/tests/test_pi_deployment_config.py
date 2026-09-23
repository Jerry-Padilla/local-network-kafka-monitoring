from pathlib import Path

from netpulse_agent.config import load_config


ROOT = Path(__file__).resolve().parents[3]


def test_physical_pi_config_uses_authorized_lan_endpoints_and_durable_outbox() -> None:
    config = load_config(ROOT / "config" / "agent-pi.yaml", environ={})

    assert config.agent.agent_id == "network-agent-ethernet-01"
    assert config.agent.role == "wired_reference"
    assert config.kafka.bootstrap_servers == "192.168.1.198:29092"
    assert config.outbox.path == Path("/var/lib/netpulse-agent/outbox.db")
    assert config.outbox.maximum_bytes == 268_435_456
    assert config.privacy.ssid == "omit"
    assert config.privacy.bssid == "omit"
    assert config.privacy.include_target_addresses is False
    assert [(item.endpoint_id, item.address) for item in config.collectors.router_ping.endpoints] == [
        ("router", "192.168.1.254")
    ]
    assert [(item.endpoint_id, item.address) for item in config.collectors.external_ping.endpoints] == [
        ("public-dns-a", "1.1.1.1")
    ]
    assert config.collectors.dns.enabled is False
    assert config.collectors.http.enabled is False
    assert config.collectors.wifi.enabled is False
    assert config.collectors.heartbeat.enabled is True
    assert config.collectors.speed_test.enabled is False


def test_physical_pi_config_contains_no_documentation_networks() -> None:
    text = (ROOT / "config" / "agent-pi.yaml").read_text(encoding="utf-8")
    assert "192.0.2." not in text
    assert "198.51.100." not in text
    assert "203.0.113." not in text
