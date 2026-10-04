from __future__ import annotations

from pathlib import Path
from runpy import run_path
from typing import Any, cast

import psycopg
import pytest
import yaml

pytest_plugins = ("pytester",)

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
    tests = services["tests"]
    test_environment = tests["environment"]

    assert tests["entrypoint"] == ["python", "scripts/query_api_test_entrypoint.py"]
    assert "NETPULSE_QUERY_API_DATABASE_URL" not in test_environment
    assert test_environment["QUERY_API_DATABASE_USER"] == "netpulse_query_api"
    assert test_environment["QUERY_API_DATABASE_PASSWORD"].startswith(
        "${QUERY_API_POSTGRES_PASSWORD"
    )
    assert test_environment["QUERY_API_DATABASE_HOST"] == "postgres"
    assert test_environment["QUERY_API_DATABASE_PORT"] == "5432"
    assert test_environment["QUERY_API_DATABASE_NAME"].startswith("${POSTGRES_DB")
    assert "NETPULSE_QUERY_API_DATABASE_URL" not in services["query-api"]["environment"]


def test_tests_only_url_builder_escapes_reserved_and_invalid_percent_characters() -> None:
    namespace = run_path(str(ROOT / "scripts" / "query_api_test_entrypoint.py"))
    build_url = namespace["build_query_api_url"]
    password = "test%GG:@/?#[]"
    url = build_url("api@test", password, "postgres", "5432", "net/pulse")

    try:
        parts = psycopg.conninfo.conninfo_to_dict(url)
    except Exception:
        parts = None
    if parts is None:
        pytest.fail("query API test URL could not be parsed", pytrace=False)
    if (
        parts.get("user") != "api@test"
        or parts.get("password") != password
        or parts.get("host") != "postgres"
        or parts.get("port") != "5432"
        or parts.get("dbname") != "net/pulse"
    ):
        pytest.fail("query API test URL changed a connection component", pytrace=False)
    if password in url or "%25GG" not in url:
        pytest.fail("query API test URL did not encode the password", pytrace=False)


@pytest.mark.parametrize("failure", ["connection", "cursor", "row", "seed", "cleanup"])
def test_acceptance_failure_output_redacts_sensitive_values(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    marker = "sensitive-value-for-test"
    monkeypatch.setenv("NETPULSE_PRIVACY_MARKER", marker)
    source = """
import os
import sys
from datetime import date
from psycopg.errors import ForeignKeyViolation

sys.path.insert(0, __TESTS_PATH__)
import test_query_api_integration as acceptance

def test_redaction(monkeypatch):
    marker = os.environ["NETPULSE_PRIVACY_MARKER"]
    case = __CASE__
    if case == "connection":
        monkeypatch.setenv("NETPULSE_INTEGRATION", "1")
        monkeypatch.setenv("NETPULSE_QUERY_API_DATABASE_URL", "postgresql://test@host/db")
        def fail_connect(_url):
            raise ValueError("connection refused for " + marker)
        monkeypatch.setattr(acceptance.psycopg, "connect", fail_connect)
        acceptance.test_dedicated_login_cannot_read_or_mutate_operational_rows()
        return

    if case in ("seed", "cleanup"):
        monkeypatch.setenv("NETPULSE_INTEGRATION", "1")
        monkeypatch.setenv("NETPULSE_ADMIN_DATABASE_URL", "test-only-admin-url")
        class FakeConnection:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, statement, _params=None):
                if case == "seed" or (case == "cleanup" and statement.startswith("DELETE")):
                    raise ForeignKeyViolation("failing fixture key " + marker)
                if statement.startswith("SELECT agent_id"):
                    self.record = ("agent", "wired_reference", "Agent")
                elif statement.startswith("SELECT endpoint_id"):
                    self.record = ("endpoint", "router", "Endpoint")
                return self
            def fetchone(self):
                return self.record
        monkeypatch.setattr(acceptance, "_connect_safely", lambda _url: FakeConnection())
        fixture = acceptance.seeded_daily.__wrapped__()
        next(fixture)
        if case == "cleanup":
            next(fixture)
        return

    seeded = acceptance.SeededDaily(date(2099, 1, 1), "agent", "endpoint", "probe-")
    def row(index):
        return {
            "date_utc": "2099-01-01", "agent_id": marker if index == 1 else "agent",
            "endpoint_id": "endpoint", "source_kind": "network_measurement",
            "probe_type": "probe-" + str(index), "total_count": 2,
            "success_count": 1, "failure_count": 1, "success_rate_pct": 50.0,
            "latency_count": 0, "latency_sum_ms": None, "mean_latency_ms": None,
            "packet_loss_count": 0, "packet_loss_sum_pct": None,
            "mean_packet_loss_pct": None,
        }
    first = {"limit": 2, "items": [row(0), row(1)],
             "next_cursor": {"opaque": marker} if case == "cursor" else "opaque"}
    second = {"limit": 2, "items": [row(2)], "next_cursor": None}
    responses = iter([(200, {"status": "ok"}), (200, first), (200, second)])
    monkeypatch.setattr(acceptance, "_get", lambda *_args, **_kwargs: next(responses))
    acceptance.test_live_http_filters_types_and_cursor(seeded)
"""
    source = source.replace("__TESTS_PATH__", repr(str(ROOT / "tests")))
    source = source.replace("__CASE__", repr(failure))
    pytester.makepyfile(test_privacy=source)
    for name in (
        "COV_CORE_SOURCE",
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COV_CORE_BRANCH",
        "COV_CORE_CONTEXT",
    ):
        monkeypatch.delenv(name, raising=False)
    result = pytester.runpytest_subprocess("-p", "no:cov", "-q", "--tb=short", "test_privacy.py")
    assert result.ret == 1
    output = result.stdout.str() + result.stderr.str()
    expected = {
        "connection": "database connection failed",
        "cursor": "first page cursor was invalid",
        "row": "agent or endpoint filter was not honored",
        "seed": "query API fixture seed failed",
        "cleanup": "query API fixture cleanup failed",
    }[failure]
    if marker in output:
        pytest.fail("acceptance failure output exposed a sensitive value", pytrace=False)
    if expected not in output:
        pytest.fail("privacy regression did not reach its intended failure", pytrace=False)
