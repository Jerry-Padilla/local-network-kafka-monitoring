from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8")),
    )


def test_airflow_profile_is_lightweight_isolated_and_loopback_only() -> None:
    services = _compose()["services"]
    airflow_services = {
        "airflow-postgres",
        "airflow-netpulse-init",
        "airflow-init",
        "airflow-fixture",
        "airflow-scheduler",
        "airflow-dag-processor",
        "airflow-api-server",
    }
    assert all(services[name]["profiles"] == ["airflow"] for name in airflow_services)
    assert "ports" not in services["airflow-postgres"]
    assert services["airflow-api-server"]["ports"] == ["127.0.0.1:8080:8080"]
    assert "airflow-worker" not in services
    assert "redis" not in services
    assert services["airflow-fixture"]["restart"] == "no"


def test_airflow_runtime_uses_local_executor_separate_metadata_and_read_only_dags() -> None:
    services = _compose()["services"]
    scheduler = services["airflow-scheduler"]
    environment = scheduler["environment"]

    assert environment["AIRFLOW__CORE__EXECUTOR"] == "LocalExecutor"
    assert "@airflow-postgres:5432/airflow" in environment["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"]
    assert environment["NETPULSE_DATABASE_URL"].startswith("postgresql://netpulse_airflow:")
    assert "POSTGRES_ADMIN_PASSWORD" not in environment
    assert "./deployment/airflow/dags:/opt/airflow/dags:ro" in scheduler["volumes"]
    assert "airflow-logs:/opt/airflow/logs" in scheduler["volumes"]
    assert scheduler["depends_on"]["airflow-init"]["condition"] == (
        "service_completed_successfully"
    )
    assert scheduler["depends_on"]["airflow-api-server"]["condition"] == ("service_healthy")
    assert len(environment["AIRFLOW__API_AUTH__JWT_SECRET"]) >= 64


def test_netpulse_login_is_reprovisioned_after_migration_for_existing_volumes() -> None:
    provision = _compose()["services"]["airflow-netpulse-init"]

    assert provision["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert provision["entrypoint"] == [
        "bash",
        "/scripts/provision-airflow-analytics-user.sh",
    ]
    assert (
        "./database/init/03-create-airflow-analytics-user.sh:"
        "/scripts/provision-airflow-analytics-user.sh:ro"
    ) in provision["volumes"]


def test_example_environment_documents_airflow_security_and_quality_settings() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for setting in (
        "AIRFLOW_METADATA_DB_PASSWORD=change-me-local-airflow-metadata",
        "AIRFLOW_NETPULSE_DB_PASSWORD=change-me-local-airflow-app",
        "AIRFLOW_API_JWT_SECRET=change-me-local-airflow-jwt-secret-at-least-64-bytes-long-0123456789abcdef",
        "AIRFLOW_ADMIN_USERNAME=admin",
        "NETPULSE_AIRFLOW_STALE_AFTER_SECONDS=900",
        "NETPULSE_AIRFLOW_DELAY_AFTER_SECONDS=600",
    ):
        assert setting in example
    assert "NETPULSE_AIRFLOW_FAILURE_WEBHOOK_URL=" in example


def test_analytics_dependencies_are_compatible_with_airflow_runtime() -> None:
    project = (ROOT / "services/analytics/pyproject.toml").read_text(encoding="utf-8")

    assert '"psycopg[binary]>=3.2.6,<4"' in project
    assert '"structlog>=25.2.0,<27"' in project
