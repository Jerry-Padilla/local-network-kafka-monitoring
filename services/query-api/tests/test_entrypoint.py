from __future__ import annotations

from importlib import import_module

import pytest
from psycopg.conninfo import conninfo_to_dict
from pytest import MonkeyPatch


def test_main_encodes_connection_components_and_execs_uvicorn(monkeypatch: MonkeyPatch) -> None:
    try:
        entrypoint = import_module("netpulse_query_api.entrypoint")
    except ImportError as error:
        pytest.fail(f"query API entrypoint is missing: {error}")

    password = "secret%41/@pass"
    monkeypatch.setenv("QUERY_API_DATABASE_USER", "netpulse_query_api")
    monkeypatch.setenv("QUERY_API_DATABASE_PASSWORD", password)
    monkeypatch.setenv("QUERY_API_DATABASE_HOST", "postgres")
    monkeypatch.setenv("QUERY_API_DATABASE_PORT", "5432")
    monkeypatch.setenv("QUERY_API_DATABASE_NAME", "netpulse")
    captured: dict[str, object] = {}

    def capture_execvp(file: str, args: list[str]) -> None:
        captured["file"] = file
        captured["args"] = args
        captured["environment"] = entrypoint.os.environ.copy()

    monkeypatch.setattr(entrypoint.os, "execvp", capture_execvp)

    entrypoint.main()

    environment = captured["environment"]
    assert isinstance(environment, dict)
    connection_info = conninfo_to_dict(environment["NETPULSE_DATABASE_URL"])
    assert connection_info["user"] == "netpulse_query_api"
    assert connection_info["password"] == password
    assert connection_info["host"] == "postgres"
    assert connection_info["port"] == "5432"
    assert connection_info["dbname"] == "netpulse"
    assert captured["file"] == "uvicorn"
    assert captured["args"] == [
        "uvicorn",
        "netpulse_query_api.main:create_app",
        "--factory",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
