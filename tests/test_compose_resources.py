from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _services() -> dict[str, Any]:
    document = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    return cast(dict[str, Any], document["services"])


def test_long_running_local_services_have_overridable_memory_ceiling() -> None:
    services = _services()
    expected_limits = {
        "postgres": "${POSTGRES_MEMORY_LIMIT:-384m}",
        "kafka": "${KAFKA_MEMORY_LIMIT:-768m}",
        "event-ingestor": "${EVENT_INGESTOR_MEMORY_LIMIT:-256m}",
        "query-api": "${QUERY_API_MEMORY_LIMIT:-256m}",
        "postgres-exporter": "${POSTGRES_EXPORTER_MEMORY_LIMIT:-128m}",
        "kafka-exporter": "${KAFKA_EXPORTER_MEMORY_LIMIT:-128m}",
        "alertmanager": "${ALERTMANAGER_MEMORY_LIMIT:-128m}",
        "prometheus": "${PROMETHEUS_MEMORY_LIMIT:-384m}",
        "grafana": "${GRAFANA_MEMORY_LIMIT:-768m}",
    }

    assert {
        service_name: services[service_name].get("mem_limit") for service_name in expected_limits
    } == expected_limits


def test_kafka_heap_leaves_native_headroom_below_its_container_limit() -> None:
    kafka = _services()["kafka"]

    assert kafka["environment"]["KAFKA_HEAP_OPTS"] == "-Xms256m -Xmx512m"
    assert kafka["mem_limit"] == "${KAFKA_MEMORY_LIMIT:-768m}"


def test_grafana_loads_only_the_datasource_backends_netpulse_uses() -> None:
    grafana = _services()["grafana"]
    environment = grafana["environment"]
    disabled = set(environment["GF_PLUGINS_DISABLE_PLUGINS"].split(","))

    assert environment["GF_PLUGINS_PREINSTALL"] == "grafana-postgresql-datasource,prometheus"
    assert disabled == {
        "elasticsearch",
        "grafana-advisor-app",
        "grafana-exploretraces-app",
        "grafana-lokiexplore-app",
        "grafana-metricsdrilldown-app",
        "grafana-pyroscope-app",
        "grafana-pyroscope-datasource",
        "influxdb",
        "jaeger",
        "loki",
        "mssql",
        "mysql",
        "opentsdb",
        "stackdriver",
        "tempo",
        "zipkin",
    }
    assert {"grafana-postgresql-datasource", "prometheus"}.isdisjoint(disabled)
