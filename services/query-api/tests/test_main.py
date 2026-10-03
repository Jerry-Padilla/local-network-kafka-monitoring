"""Production application lifecycle contract."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from netpulse_query_api import main
from netpulse_query_api.config import QueryApiConfig


def test_builder_accepts_injected_lifespan() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        events.append("started")
        yield
        events.append("stopped")

    class Repository:
        async def health(self) -> bool:
            return True

        async def list_daily(self, *_args: object) -> None:
            raise AssertionError("not needed")

    with TestClient(main.build_app(Repository(), lifespan=lifespan)) as client:
        assert client.get("/healthz").status_code == 200
        assert events == ["started"]
    assert events == ["started", "stopped"]


def test_create_app_opens_and_closes_bounded_read_only_pool(monkeypatch: object) -> None:
    events: list[str] = []
    captured: dict[str, object] = {}
    config = QueryApiConfig(
        database_url="postgresql://user:password@host/db",
        pool_min_size=2,
        pool_max_size=4,
        pool_acquire_timeout_seconds=1.5,
        statement_timeout_ms=2500,
    )

    class Pool:
        def __init__(self, conninfo: str, **kwargs: object) -> None:
            captured["conninfo"] = conninfo
            captured.update(kwargs)

        async def open(self) -> None:
            events.append("opened")

        async def close(self) -> None:
            events.append("closed")

    monkeypatch.setattr(main.QueryApiConfig, "from_env", lambda: config)  # type: ignore[attr-defined]
    monkeypatch.setattr(main, "AsyncConnectionPool", Pool)  # type: ignore[attr-defined]
    with TestClient(main.create_app()) as client:
        assert events == ["opened"]
        assert client.get("/openapi.json").status_code == 200
    assert events == ["opened", "closed"]
    assert captured["conninfo"] == config.database_url
    assert captured["min_size"] == 2
    assert captured["max_size"] == 4
    assert captured["timeout"] == 1.5
    assert captured["open"] is False
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["options"] == "-c default_transaction_read_only=on"
