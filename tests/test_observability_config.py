from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
OBSERVABILITY = ROOT / "deployment" / "observability"


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _network_panels() -> dict[str, dict]:
    dashboard = json.loads(
        (OBSERVABILITY / "grafana" / "dashboards" / "network-reliability.json").read_text(
            encoding="utf-8"
        )
    )
    return {panel["title"]: panel for panel in dashboard["panels"]}


def _live_query_rows(title: str) -> list[dict]:
    # Execute the configured SQL; only Grafana's time macro needs expansion.
    # Same agent/target across probe types exposes any conflated series legends.
    query = _network_panels()[title]["targets"][0]["rawSql"].replace(
        "$__timeFilter(event_time)", "event_time BETWEEN '2026-10-06T12:00' AND '2026-10-06T13:00'"
    )
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE v_grafana_live_measurements "
            "(event_time TEXT, agent_id TEXT, target_id TEXT, measurement_type TEXT, "
            "success BOOLEAN, latency_ms REAL, packet_loss_pct REAL, jitter_ms REAL)"
        )
        connection.executemany(
            "INSERT INTO v_grafana_live_measurements VALUES (?, 'agent', 'target', ?, ?, ?, ?, 1)",
            [
                ("2026-10-06T12:01", "router_ping", True, 4, 0),
                ("2026-10-06T12:02", "external_ping", False, 20, 50),
                ("2026-10-06T12:03", "wifi_diagnostics", False, 8, 100),
                ("2026-10-06T12:04", "router_ping", False, None, 100),
                ("2026-10-06T11:59", "external_ping", True, 10, 0),
            ],
        )
        return [dict(row) for row in connection.execute(query)]


@pytest.mark.parametrize("title", ["Live Latency", "Live Packet Loss", "Live Probe Success"])
def test_live_series_distinguish_measurement_types(title: str) -> None:
    rows = _live_query_rows(title)
    assert rows[0]["metric"] == "agent / target / router_ping"
    assert rows[1]["metric"] == "agent / target / external_ping"
    assert len({row["metric"] for row in rows[:2]}) == 2
    if title != "Live Packet Loss":
        assert rows[2]["metric"] == "agent / target / wifi_diagnostics"


def test_live_packet_loss_excludes_wifi_connection_state() -> None:
    assert [row["value"] for row in _live_query_rows("Live Packet Loss")] == [0, 50, 100]


def test_live_queries_preserve_event_time_values_and_latest_order() -> None:
    latency = _live_query_rows("Live Latency")
    assert [row["time"] for row in latency] == [
        "2026-10-06T12:01",
        "2026-10-06T12:02",
        "2026-10-06T12:03",
    ]
    assert [row["value"] for row in latency] == [4, 20, 8]
    assert [row["value"] for row in _live_query_rows("Live Probe Success")] == [100, 0, 0, 0]
    latest = _live_query_rows("Latest Readings")
    assert [row["event_time"] for row in latest] == [
        "2026-10-06T12:04",
        "2026-10-06T12:03",
        "2026-10-06T12:02",
        "2026-10-06T12:01",
    ]
    assert latest[1]["measurement_type"] == "wifi_diagnostics"


def test_network_panels_use_millisecond_and_percentage_units() -> None:
    panels = _network_panels()
    for title, unit in (
        ("Probe Success", "percent"),
        ("Live Latency", "ms"),
        ("Live Packet Loss", "percent"),
        ("Live Probe Success", "percent"),
    ):
        assert panels[title].get("fieldConfig", {}).get("defaults", {}).get("unit") == unit
    overrides = panels["Latest Readings"].get("fieldConfig", {}).get("overrides", [])
    units = {
        override["matcher"]["options"]: prop["value"]
        for override in overrides
        if override["matcher"]["id"] == "byName"
        for prop in override["properties"]
        if prop["id"] == "unit"
    }
    assert units == {"latency_ms": "ms", "jitter_ms": "ms", "packet_loss_pct": "percent"}


@pytest.mark.parametrize(
    "title", ["Live Latency", "Live Packet Loss", "Live Probe Success", "Latest Readings"]
)
def test_live_panel_descriptions_explain_event_time_and_replay(title: str) -> None:
    description = _network_panels()[title].get("description", "").lower()
    assert "ingested" in description
    assert "event time" in description
    assert "replay" in description
    assert "no production sla" in description
    assert "continuous real-time delivery" in description
    if title in {"Live Packet Loss", "Latest Readings"}:
        assert "wi-fi" in description and "connection state" in description


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
    assert services["kafka"]["ports"][0].startswith("${KAFKA_EXTERNAL_BIND_ADDRESS:-127.0.0.1}:")


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
    assert (
        "POSTGRES_EXPORTER_PASSWORD"
        in services["postgres-exporter"]["environment"]["DATA_SOURCE_PASS"]
    )
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

    assert jobs["event-ingestor"]["static_configs"][0]["targets"] == ["event-ingestor:9101"]
    assert jobs["network-agent"]["static_configs"][0]["targets"] == ["network-agent:9102"]
    assert jobs["stream-processor"]["static_configs"][0]["targets"] == ["stream-processor:9103"]
    assert jobs["incident-classifier"]["static_configs"][0]["targets"] == [
        "incident-classifier:9104"
    ]
    assert jobs["postgres-exporter"]["static_configs"][0]["targets"] == ["postgres-exporter:9187"]
    assert jobs["kafka-exporter"]["static_configs"][0]["targets"] == ["kafka-exporter:9308"]
    assert jobs["pi-agent"]["file_sd_configs"][0]["files"] == ["/etc/prometheus/pi-targets.json"]
    assert (
        json.loads((OBSERVABILITY / "prometheus" / "pi-targets.json").read_text(encoding="utf-8"))
        == []
    )


def test_grafana_datasources_are_provisioned_from_environment() -> None:
    datasources = yaml.safe_load(
        (OBSERVABILITY / "grafana" / "provisioning" / "datasources" / "datasources.yml").read_text(
            encoding="utf-8"
        )
    )["datasources"]
    by_uid = {item["uid"]: item for item in datasources}

    assert by_uid["prometheus"]["isDefault"] is True
    assert by_uid["prometheus"]["url"] == "http://prometheus:9090"
    assert by_uid["postgres"]["user"] == "netpulse_grafana"
    assert by_uid["postgres"]["secureJsonData"]["password"] == "$GRAFANA_POSTGRES_PASSWORD"
    assert by_uid["postgres"]["jsonData"]["database"] == "$POSTGRES_DB"


def test_grafana_mounts_only_owned_provisioning_subdirectories() -> None:
    volumes = _compose()["services"]["grafana"]["volumes"]

    assert (
        "./deployment/observability/grafana/provisioning/datasources:"
        "/etc/grafana/provisioning/datasources:ro"
    ) in volumes
    assert (
        "./deployment/observability/grafana/provisioning/dashboards:"
        "/etc/grafana/provisioning/dashboards:ro"
    ) in volumes
    assert not any(
        volume.startswith("./deployment/observability/grafana/provisioning:") for volume in volumes
    )


def test_recording_rules_cover_objectives_and_zero_traffic_guards() -> None:
    rules = yaml.safe_load(
        (OBSERVABILITY / "prometheus" / "rules" / "recording.yml").read_text(encoding="utf-8")
    )
    records = {rule["record"]: rule["expr"] for group in rules["groups"] for rule in group["rules"]}

    assert {
        "netpulse:ingestion_success_ratio:5m",
        "netpulse:ingestion_processing_p95_seconds:5m",
        "netpulse:ingestion_freshness_seconds",
        "netpulse:kafka_consumer_lag",
        "netpulse:ingestion_error_budget_burn:5m",
    } <= records.keys()
    assert "clamp_min" in records["netpulse:ingestion_success_ratio:5m"]
    assert "histogram_quantile(0.95" in records["netpulse:ingestion_processing_p95_seconds:5m"]


def test_alerts_are_actionable_and_empty_pi_discovery_is_safe() -> None:
    rules = yaml.safe_load(
        (OBSERVABILITY / "prometheus" / "rules" / "alerts.yml").read_text(encoding="utf-8")
    )
    alerts = {rule["alert"]: rule for group in rules["groups"] for rule in group["rules"]}
    expected = {
        "NetPulseTargetDown",
        "NetPulsePostgresUnavailable",
        "NetPulseKafkaConsumerLag",
        "NetPulsePipelineStale",
        "NetPulseDeadLetterGrowth",
        "NetPulseIngestionFailures",
        "NetPulseClassifierStalled",
        "NetPulseIncidentOutboxBacklog",
        "NetPulsePiStale",
        "NetPulsePiOutboxBacklog",
    }
    assert expected <= alerts.keys()
    for name in expected:
        alert = alerts[name]
        assert alert["labels"]["severity"] in {"warning", "critical"}
        assert {"summary", "impact", "likely_cause", "runbook_url"} <= alert["annotations"].keys()
        assert alert["annotations"]["runbook_url"].startswith("https://github.com/")
    assert 'required="true"' in alerts["NetPulseTargetDown"]["expr"]
    assert "and on()" in alerts["NetPulsePipelineStale"]["expr"]
    assert 'count(up{job="pi-agent"}) > 0' in alerts["NetPulsePiStale"]["expr"]
    assert "and on()" in alerts["NetPulsePiStale"]["expr"]
    assert (
        json.loads((OBSERVABILITY / "prometheus" / "pi-targets.json").read_text(encoding="utf-8"))
        == []
    )


def test_three_dashboards_are_provisioned_with_required_panels_and_datasources() -> None:
    provider = yaml.safe_load(
        (OBSERVABILITY / "grafana" / "provisioning" / "dashboards" / "provider.yml").read_text(
            encoding="utf-8"
        )
    )
    assert provider["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards"

    expectations = {
        "platform-health.json": (
            "netpulse-platform-health",
            {"Scrape Targets", "PostgreSQL Health", "Kafka Brokers"},
        ),
        "pipeline-reliability.json": (
            "netpulse-pipeline-reliability",
            {"Ingestion Throughput", "Consumer Lag", "Ingestion Success Ratio", "p95 Processing"},
        ),
        "network-reliability.json": (
            "netpulse-network-reliability",
            {
                "Probe Success",
                "Live Latency",
                "Live Packet Loss",
                "Live Probe Success",
                "Latest Readings",
                "Agent Freshness",
                "Current Incidents",
                "Pi Outbox",
            },
        ),
    }
    allowed_views = {
        "v_daily_probe_reliability",
        "v_incident_summary",
        "v_sre_agent_status",
        "v_sre_pipeline_status",
        "v_grafana_live_measurements",
    }
    for filename, (uid, required_titles) in expectations.items():
        dashboard = json.loads(
            (OBSERVABILITY / "grafana" / "dashboards" / filename).read_text(encoding="utf-8")
        )
        assert dashboard["uid"] == uid
        assert dashboard["title"].startswith("NetPulse")
        titles = {panel["title"] for panel in dashboard["panels"]}
        assert required_titles <= titles
        for panel in dashboard["panels"]:
            assert panel["datasource"]["uid"] in {"prometheus", "postgres"}
            for target in panel.get("targets", []):
                if "rawSql" in target:
                    sql_text = target["rawSql"].lower()
                    assert any(view in sql_text for view in allowed_views)
                    referenced_relations = re.findall(
                        r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", sql_text
                    )
                    assert set(referenced_relations) <= allowed_views
    network_dashboard = json.loads(
        (OBSERVABILITY / "grafana" / "dashboards" / "network-reliability.json").read_text(
            encoding="utf-8"
        )
    )
    assert network_dashboard["time"] == {"from": "now-1h", "to": "now"}
    assert network_dashboard["refresh"] == "10s"
    daily_panel = next(
        panel for panel in network_dashboard["panels"] if panel["title"] == "Probe Success"
    )
    assert daily_panel["timeFrom"] == "30d"
    live_titles = {"Live Latency", "Live Packet Loss", "Live Probe Success", "Latest Readings"}
    live_panels = [panel for panel in network_dashboard["panels"] if panel["title"] in live_titles]
    assert {panel["title"] for panel in live_panels} == live_titles
    for panel in live_panels:
        for target in panel["targets"]:
            assert "from v_grafana_live_measurements" in target["rawSql"].lower()
            assert "$__timefilter(event_time)" in target["rawSql"].lower()
    network = json.dumps(network_dashboard)
    assert "date_utc" in network and "success_rate_pct" in network
    assert "start_time" in network
    assert "bucket_date" not in network and "opened_at" not in network


def test_every_alert_runbook_has_operational_sections_and_no_destructive_reset() -> None:
    runbooks = (
        "target-down.md",
        "kafka-lag.md",
        "postgres-unavailable.md",
        "pipeline-stale.md",
        "dead-letter-growth.md",
        "classifier-stalled.md",
        "incident-outbox-backlog.md",
        "pi-stale.md",
        "pi-outbox-backlog.md",
    )
    for filename in runbooks:
        text = (ROOT / "docs" / "runbooks" / filename).read_text(encoding="utf-8")
        for heading in (
            "## Symptoms",
            "## Safety",
            "## Diagnosis",
            "## Remediation",
            "## Recovery verification",
            "## Escalation",
        ):
            assert heading in text
        assert "docker compose down -v" not in text
        assert "reset --hard" not in text
