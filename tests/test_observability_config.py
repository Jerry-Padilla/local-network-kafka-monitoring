from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OBSERVABILITY = ROOT / "deployment" / "observability"


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_monitoring_profile_uses_pinned_images_and_private_ports() -> None:
    compose = _compose()
    services = compose["services"]
    expected_images = {
        "prometheus": "prom/prometheus:v3.14.0",
        "alertmanager": "prom/alertmanager:v0.34.1",
        "grafana": "grafana/grafana:13.2.2",
        "postgres-exporter": "prometheuscommunity/postgres-exporter:v0.20.1",
        "kafka-exporter": "danielqsj/kafka-exporter:v1.10.0",
        "monitoring-init": "postgres:17.10-bookworm",
    }

    for service_name, image in expected_images.items():
        service = services[service_name]
        assert service["image"] == image
        assert service["profiles"] == ["monitoring"]
        assert ":latest" not in image

    assert services["prometheus"]["ports"] == ["127.0.0.1:9090:9090"]
    assert services["alertmanager"]["ports"] == ["127.0.0.1:9093:9093"]
    assert services["grafana"]["ports"] == ["127.0.0.1:3000:3000"]
    assert "ports" not in services["postgres-exporter"]
    assert "ports" not in services["kafka-exporter"]
    assert services["postgres"]["ports"][0].startswith("127.0.0.1:")
    assert services["kafka"]["ports"][0].startswith(
        "${KAFKA_EXTERNAL_BIND_ADDRESS:-127.0.0.1}:"
    )


def test_monitoring_services_have_storage_healthchecks_and_safe_credentials() -> None:
    compose = _compose()
    services = compose["services"]
    volumes = compose["volumes"]

    for volume in ("prometheus-data", "alertmanager-data", "grafana-data"):
        assert volume in volumes
    for service in ("prometheus", "alertmanager", "grafana"):
        assert "healthcheck" in services[service]
    assert "GRAFANA_POSTGRES_PASSWORD" in services["grafana"]["environment"]
    assert services["postgres-exporter"]["environment"]["DATA_SOURCE_USER"] == (
        "netpulse_postgres_exporter"
    )
    assert "POSTGRES_EXPORTER_PASSWORD" in services["postgres-exporter"]["environment"][
        "DATA_SOURCE_PASS"
    ]
    assert "change-me-local-admin" not in str(services["grafana"])
    assert "change-me-local-admin" not in str(services["postgres-exporter"])


def test_application_metrics_use_internal_ports_without_new_host_bindings() -> None:
    services = _compose()["services"]
    expected_ports = {
        "event-ingestor": "9101",
        "network-agent": "9102",
        "stream-processor": "9103",
        "incident-classifier": "9104",
    }

    for service_name, port in expected_ports.items():
        service = services[service_name]
        environment = service["environment"]
        assert environment["NETPULSE_METRICS_ENABLED"] == "true"
        assert environment["NETPULSE_METRICS_HOST"] == "0.0.0.0"
        assert environment["NETPULSE_METRICS_PORT"] == port
        assert "ports" not in service


def test_prometheus_scrapes_internal_services_and_empty_pi_file_sd() -> None:
    prometheus = yaml.safe_load(
        (OBSERVABILITY / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
    )
    jobs = {item["job_name"]: item for item in prometheus["scrape_configs"]}

    assert jobs["event-ingestor"]["static_configs"][0]["targets"] == [
        "event-ingestor:9101"
    ]
    assert jobs["network-agent"]["static_configs"][0]["targets"] == [
        "network-agent:9102"
    ]
    assert jobs["stream-processor"]["static_configs"][0]["targets"] == [
        "stream-processor:9103"
    ]
    assert jobs["incident-classifier"]["static_configs"][0]["targets"] == [
        "incident-classifier:9104"
    ]
    assert jobs["postgres-exporter"]["static_configs"][0]["targets"] == [
        "postgres-exporter:9187"
    ]
    assert jobs["kafka-exporter"]["static_configs"][0]["targets"] == [
        "kafka-exporter:9308"
    ]
    assert jobs["pi-agent"]["file_sd_configs"][0]["files"] == [
        "/etc/prometheus/pi-targets.json"
    ]
    assert json.loads(
        (OBSERVABILITY / "prometheus" / "pi-targets.json").read_text(encoding="utf-8")
    ) == []


def test_grafana_datasources_are_provisioned_from_environment() -> None:
    datasources = yaml.safe_load(
        (
            OBSERVABILITY
            / "grafana"
            / "provisioning"
            / "datasources"
            / "datasources.yml"
        ).read_text(encoding="utf-8")
    )["datasources"]
    by_uid = {item["uid"]: item for item in datasources}

    assert by_uid["prometheus"]["isDefault"] is True
    assert by_uid["prometheus"]["url"] == "http://prometheus:9090"
    assert by_uid["postgres"]["user"] == "netpulse_grafana"
    assert by_uid["postgres"]["secureJsonData"]["password"] == "$GRAFANA_POSTGRES_PASSWORD"
    assert by_uid["postgres"]["jsonData"]["database"] == "$POSTGRES_DB"
