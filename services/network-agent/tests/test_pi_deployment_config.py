import tomllib
from pathlib import Path

import yaml
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
    router_endpoints = [
        (item.endpoint_id, item.address)
        for item in config.collectors.router_ping.endpoints
    ]
    assert router_endpoints == [
        ("router", "192.168.1.254")
    ]
    external_endpoints = [
        (item.endpoint_id, item.address)
        for item in config.collectors.external_ping.endpoints
    ]
    assert external_endpoints == [
        ("public-dns-a", "1.1.1.1")
    ]
    assert config.collectors.dns.enabled is True
    assert [
        (item.endpoint_id, item.domain, item.resolver)
        for item in config.collectors.dns.endpoints
    ] == [("dns-check", "example.com", "192.168.1.254")]
    assert config.collectors.http.enabled is False
    assert config.collectors.wifi.enabled is False
    assert config.collectors.heartbeat.enabled is True
    assert config.collectors.speed_test.enabled is False


def test_physical_pi_config_contains_no_documentation_networks() -> None:
    text = (ROOT / "config" / "agent-pi.yaml").read_text(encoding="utf-8")
    assert "192.0.2." not in text
    assert "198.51.100." not in text
    assert "203.0.113." not in text


def test_docker_agent_is_a_bounded_container_probe() -> None:
    config = load_config(ROOT / "config" / "agent-docker.yaml", environ={})

    assert config.agent.agent_id == "container-observer-01"
    assert config.agent.role.value == "container_probe"
    assert config.collectors.wifi.enabled is False
    assert config.collectors.http.enabled is False
    assert config.collectors.speed_test.enabled is False
    assert config.collectors.heartbeat.enabled is True
    assert config.collectors.dns.enabled is True


def test_compose_uses_docker_fixture_and_internal_metrics_endpoint() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    agent = compose["services"]["network-agent"]

    assert "./config/agent-docker.yaml:/etc/netpulse-agent/agent.yaml:ro" in agent["volumes"]
    assert agent["environment"]["NETPULSE_METRICS_ENABLED"] == "true"
    assert agent["environment"]["NETPULSE_METRICS_HOST"] == "0.0.0.0"
    assert agent["environment"]["NETPULSE_METRICS_PORT"] == "9102"
    assert "ports" not in agent


def test_pi_bootstrap_environment_enables_lan_metrics_without_secrets() -> None:
    template = (
        ROOT / "deployment" / "pi" / "bootstrap" / "agent.env.example"
    ).read_text(encoding="utf-8")

    assert "NETPULSE_METRICS_ENABLED=true" in template
    assert "NETPULSE_METRICS_HOST=0.0.0.0" in template
    assert "NETPULSE_METRICS_PORT=9102" in template
    assert "SALT" not in template.upper()


def test_first_boot_requires_and_installs_staged_environment_idempotently() -> None:
    script = (
        ROOT / "deployment" / "pi" / "bootstrap" / "first-boot.sh"
    ).read_text(encoding="utf-8")

    requirement = 'if [[ ! -f "$BUNDLE/agent.env" ]]'
    completion_guard = 'if [[ -f "$SUCCESS_MARKER" ]]'
    installation = 'install -o root -g root -m 0640 "$BUNDLE/agent.env"'
    assert requirement in script
    assert installation in script
    assert script.index(completion_guard) < script.index(requirement) < script.index(installation)


def test_pi_python_313_can_install_agent_and_observability_packages() -> None:
    agent_project = tomllib.loads(
        (ROOT / "services" / "network-agent" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    observability_project = tomllib.loads(
        (ROOT / "packages" / "observability" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert agent_project["project"]["requires-python"] == ">=3.12,<3.14"
    assert observability_project["project"]["requires-python"] == ">=3.12,<3.14"


def test_service_images_install_the_local_observability_package() -> None:
    for relative in (
        Path("services/event-ingestor/Dockerfile"),
        Path("services/network-agent/Dockerfile"),
    ):
        dockerfile = (ROOT / relative).read_text(encoding="utf-8")
        assert "COPY packages/observability /app/packages/observability" in dockerfile
        assert "/app/packages/observability" in dockerfile
