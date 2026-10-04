from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _services() -> dict[str, Any]:
    document = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    return cast(dict[str, Any], document["services"])


def test_api_profile_provisions_after_migration_then_starts_api() -> None:
    services = _services()
    provision = services["query-api-init"]
    api = services["query-api"]

    assert provision["profiles"] == ["api"]
    assert api["profiles"] == ["api"]
    assert provision["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert api["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert api["depends_on"]["query-api-init"]["condition"] == "service_completed_successfully"
    assert provision["restart"] == "no"
    assert provision["entrypoint"] == ["bash", "/scripts/provision-query-api-user.sh"]
    assert (
        "./database/init/02-create-query-api-user.sh:/scripts/provision-query-api-user.sh:ro"
        in provision["volumes"]
    )


def test_api_gets_only_dedicated_login_and_private_port() -> None:
    services = _services()
    postgres_env = services["postgres"]["environment"]
    provision_env = services["query-api-init"]["environment"]
    api = services["query-api"]
    api_env = api["environment"]

    assert "QUERY_API_POSTGRES_PASSWORD" in postgres_env
    assert "QUERY_API_POSTGRES_PASSWORD" in provision_env
    assert "PGPASSWORD" in provision_env
    assert "POSTGRES_USER" in provision_env
    assert "POSTGRES_DB" in provision_env
    assert set(api_env) == {
        "QUERY_API_DATABASE_USER",
        "QUERY_API_DATABASE_PASSWORD",
        "QUERY_API_DATABASE_HOST",
        "QUERY_API_DATABASE_PORT",
        "QUERY_API_DATABASE_NAME",
        "NETPULSE_QUERY_API_POOL_MIN_SIZE",
        "NETPULSE_QUERY_API_POOL_MAX_SIZE",
        "NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS",
        "NETPULSE_QUERY_API_STATEMENT_TIMEOUT_MS",
        "NETPULSE_QUERY_API_LOG_LEVEL",
    }
    assert api_env["QUERY_API_DATABASE_USER"] == "netpulse_query_api"
    assert api_env["QUERY_API_DATABASE_PASSWORD"].startswith("${QUERY_API_POSTGRES_PASSWORD")
    assert api_env["QUERY_API_DATABASE_HOST"] == "postgres"
    assert api_env["QUERY_API_DATABASE_PORT"] == "5432"
    assert api_env["QUERY_API_DATABASE_NAME"].startswith("${POSTGRES_DB")
    assert "POSTGRES_ADMIN_PASSWORD" not in str(api_env)
    assert "netpulse_app" not in str(api_env)
    assert api["ports"] == ["127.0.0.1:8000:8000"]
    assert api["networks"] == ["backend"]


def test_api_image_is_non_root_and_health_checks_local_endpoint() -> None:
    services = _services()
    api = services["query-api"]
    dockerfile = (ROOT / "services" / "query-api" / "Dockerfile").read_text(encoding="utf-8")

    assert api["build"]["dockerfile"] == "services/query-api/Dockerfile"
    assert "FROM python:3.12.10-slim-bookworm" in dockerfile
    assert "COPY services/query-api" in dockerfile
    assert "10001" in dockerfile
    assert "USER netpulse" in dockerfile
    assert 'CMD ["python", "-m", "netpulse_query_api.entrypoint"]' in dockerfile
    assert "urllib.request" in str(api["healthcheck"]["test"])
    assert "http://127.0.0.1:8000/healthz" in str(api["healthcheck"]["test"])


def test_example_environment_documents_api_password_and_tuning() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "QUERY_API_POSTGRES_PASSWORD=change-me-local-query-api" in example
    assert "NETPULSE_QUERY_API_POOL_MIN_SIZE=1" in example
    assert "NETPULSE_QUERY_API_POOL_MAX_SIZE=5" in example
    assert "NETPULSE_QUERY_API_POOL_ACQUIRE_TIMEOUT_SECONDS=2.0" in example
    assert "NETPULSE_QUERY_API_STATEMENT_TIMEOUT_MS=3000" in example


def test_acceptance_container_receives_dedicated_api_login_only() -> None:
    services = _services()
    test_environment = services["tests"]["environment"]

    assert test_environment["NETPULSE_QUERY_API_DATABASE_URL"] == (
        "postgresql://netpulse_query_api:"
        "${QUERY_API_POSTGRES_PASSWORD:-change-me-local-query-api}"
        "@postgres:5432/${POSTGRES_DB:-netpulse}"
    )
    assert "NETPULSE_QUERY_API_DATABASE_URL" not in services["query-api"]["environment"]
