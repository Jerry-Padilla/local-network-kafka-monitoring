"""HTTP contract for the read-only daily reliability API."""

from __future__ import annotations

import json
import logging
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from netpulse_query_api.api import build_app
from netpulse_query_api.cursor import decode_cursor, encode_cursor
from netpulse_query_api.models import (
    CursorKey,
    DailyReliabilityFilters,
    DailyReliabilityRow,
    SourceKind,
)
from netpulse_query_api.repository import ReliabilityPage
from psycopg import OperationalError, ProgrammingError
from psycopg.errors import QueryCanceled
from psycopg_pool import PoolTimeout


def _row(agent_id: str = "agent-a", endpoint_id: str = "endpoint-a") -> DailyReliabilityRow:
    return DailyReliabilityRow(
        date_utc=date(2026, 10, 1),
        agent_id=agent_id,
        endpoint_id=endpoint_id,
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type="http",
        total_count=2,
        success_count=1,
        failure_count=1,
        success_rate_pct=50.0,
        latency_count=0,
        latency_sum_ms=None,
        mean_latency_ms=None,
        packet_loss_count=0,
        packet_loss_sum_pct=None,
        mean_packet_loss_pct=None,
    )


class FakeRepository:
    def __init__(self, page: ReliabilityPage | None = None) -> None:
        self.page = page or ReliabilityPage(rows=(), has_more=False)
        self.available = True
        self.error: Exception | None = None
        self.health_calls = 0
        self.list_calls: list[tuple[DailyReliabilityFilters, CursorKey | None, int]] = []

    async def health(self) -> bool:
        self.health_calls += 1
        if self.error is not None:
            raise self.error
        return self.available

    async def list_daily(
        self, filters: DailyReliabilityFilters, cursor: CursorKey | None, limit: int
    ) -> ReliabilityPage:
        self.list_calls.append((filters, cursor, limit))
        if self.error is not None:
            raise self.error
        return self.page


def test_health_returns_ok_or_generic_unavailable_with_request_id() -> None:
    repo = FakeRepository()
    client = TestClient(build_app(repo))
    healthy = client.get("/healthz")
    assert healthy.status_code == 200
    assert healthy.json() == {"status": "ok"}
    assert re.fullmatch(r"[0-9a-f-]{36}", healthy.headers["X-Request-ID"])
    repo.available = False
    unhealthy = client.get("/healthz")
    assert unhealthy.status_code == 503
    assert unhealthy.json() == {"detail": "database unavailable"}
    assert repo.health_calls == 2


def test_daily_empty_page_defaults_to_fifty_and_populated_page_serializes_all_fields() -> None:
    repo = FakeRepository()
    client = TestClient(build_app(repo))
    empty = client.get("/v1/reliability/daily")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "next_cursor": None, "limit": 50}
    assert repo.list_calls[-1] == (DailyReliabilityFilters(), None, 50)
    repo.page = ReliabilityPage(rows=(_row(),), has_more=False)
    populated = client.get("/v1/reliability/daily?limit=200")
    assert populated.status_code == 200
    assert populated.json() == {
        "items": [
            {
                "date_utc": "2026-10-01",
                "agent_id": "agent-a",
                "endpoint_id": "endpoint-a",
                "source_kind": "service_check",
                "probe_type": "http",
                "total_count": 2,
                "success_count": 1,
                "failure_count": 1,
                "success_rate_pct": 50.0,
                "latency_count": 0,
                "latency_sum_ms": None,
                "mean_latency_ms": None,
                "packet_loss_count": 0,
                "packet_loss_sum_pct": None,
                "mean_packet_loss_pct": None,
            }
        ],
        "next_cursor": None,
        "limit": 200,
    }
    assert repo.list_calls[-1][2] == 200


def test_daily_next_cursor_uses_last_returned_row_and_filter_fingerprint() -> None:
    repo = FakeRepository(ReliabilityPage(rows=(_row(),), has_more=True))
    client = TestClient(build_app(repo))
    response = client.get("/v1/reliability/daily?agent_id=agent-a&limit=1")
    assert response.status_code == 200
    token = response.json()["next_cursor"]
    assert isinstance(token, str)
    assert decode_cursor(token, DailyReliabilityFilters(agent_id="agent-a")) == CursorKey(
        date_utc=date(2026, 10, 1),
        agent_id="agent-a",
        endpoint_id="endpoint-a",
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type="http",
    )
    second = client.get("/v1/reliability/daily", params={"agent_id": "agent-a", "cursor": token})
    assert second.status_code == 200
    assert repo.list_calls[-1][1] is not None
    assert repo.list_calls[-1][1].agent_id == "agent-a"


def test_daily_continuation_accepts_cursor_for_maximum_non_bmp_endpoint() -> None:
    row = _row(endpoint_id="\U0001f4e1" * 128)
    repo = FakeRepository(ReliabilityPage(rows=(row,), has_more=True))
    client = TestClient(build_app(repo))

    first = client.get("/v1/reliability/daily", params={"limit": "1"})
    cursor = first.json()["next_cursor"]
    second = client.get("/v1/reliability/daily", params={"limit": "1", "cursor": cursor})

    assert first.status_code == 200
    assert second.status_code == 200
    assert repo.list_calls[-1][1] is not None
    assert repo.list_calls[-1][1].endpoint_id == row.endpoint_id


def test_daily_pagination_preserves_whitespace_in_stored_ordering_keys() -> None:
    first_row = _row(agent_id=" agent ", endpoint_id=" endpoint-a ")
    second_row = _row(agent_id=" agent ", endpoint_id=" endpoint-b ")

    class PagingRepository(FakeRepository):
        async def list_daily(
            self, filters: DailyReliabilityFilters, cursor: CursorKey | None, limit: int
        ) -> ReliabilityPage:
            self.list_calls.append((filters, cursor, limit))
            if cursor is None:
                return ReliabilityPage(rows=(first_row,), has_more=True)
            assert cursor.agent_id == " agent "
            assert cursor.endpoint_id == " endpoint-a "
            return ReliabilityPage(rows=(second_row,), has_more=False)

    repo = PagingRepository()
    client = TestClient(build_app(repo))

    first = client.get("/v1/reliability/daily", params={"limit": "1"})
    second = client.get(
        "/v1/reliability/daily",
        params={"limit": "1", "cursor": first.json()["next_cursor"]},
    )

    assert first.json()["items"][0]["endpoint_id"] == " endpoint-a "
    assert second.status_code == 200
    assert second.json()["items"][0]["endpoint_id"] == " endpoint-b "


def test_daily_passes_all_exact_filters_and_inclusive_date_bounds() -> None:
    repo = FakeRepository()
    response = TestClient(build_app(repo)).get(
        "/v1/reliability/daily",
        params={
            "from_date": "2026-10-01",
            "through_date": "2026-10-02",
            "agent_id": "agent-a",
            "endpoint_id": "endpoint-a",
            "source_kind": "service_check",
            "probe_type": "http",
            "limit": "1",
        },
    )
    assert response.status_code == 200
    filters, cursor, limit = repo.list_calls[0]
    assert filters == DailyReliabilityFilters(
        from_date=date(2026, 10, 1),
        through_date=date(2026, 10, 2),
        agent_id="agent-a",
        endpoint_id="endpoint-a",
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type="http",
    )
    assert cursor is None
    assert limit == 1


@pytest.mark.parametrize(
    "params",
    [
        {"unknown": "x"},
        {"agent_id": " "},
        {"endpoint_id": " "},
        {"probe_type": " "},
        {"agent_id": "x" * 129},
        {"from_date": "2026-01-01"},
        {"through_date": "2026-01-01"},
        {"from_date": "2026-01-02", "through_date": "2026-01-01"},
        {"from_date": "2026-01-01", "through_date": "2027-01-02"},
        {"from_date": "bad", "through_date": "2026-01-01"},
        {"source_kind": "invalid"},
        {"limit": "0"},
        {"limit": "201"},
        {"limit": "nope"},
        {"limit": "9" * 5000},
    ],
)
def test_invalid_query_returns_stable_422_without_repository_access(params: dict[str, str]) -> None:
    repo = FakeRepository()
    response = TestClient(build_app(repo)).get("/v1/reliability/daily", params=params)
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid query parameters"}
    assert repo.list_calls == []


def test_invalid_or_filter_mismatched_cursor_returns_specific_422() -> None:
    repo = FakeRepository()
    client = TestClient(build_app(repo))
    invalid = client.get("/v1/reliability/daily?cursor=not-a-valid-cursor")
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "invalid cursor"}
    token = encode_cursor(_row(), DailyReliabilityFilters(agent_id="agent-a"))
    mismatch = client.get("/v1/reliability/daily", params={"cursor": token, "agent_id": "other"})
    assert mismatch.status_code == 422
    assert mismatch.json() == {"detail": "cursor does not match filters"}
    assert repo.list_calls == []


@pytest.mark.parametrize(
    "request_id,accepted",
    [
        ("abc XYZ-._~/!", True),
        ("x" * 128, True),
        ("bad\r\nid", False),
        (b"caf\xe9", False),
        ("x" * 129, False),
    ],
)
def test_request_id_accepts_only_printable_ascii_up_to_128(
    request_id: str | bytes, accepted: bool
) -> None:
    response = TestClient(build_app(FakeRepository())).get(
        "/healthz", headers={"X-Request-ID": request_id}
    )
    assert response.status_code == 200
    returned = response.headers["X-Request-ID"]
    if accepted:
        assert returned == request_id
    else:
        assert returned != request_id
        assert re.fullmatch(r"[0-9a-f-]{36}", returned)


@pytest.mark.parametrize(
    "error,expected_status,expected_detail",
    [
        (PoolTimeout("postgresql://user:password@host/db"), 503, "database unavailable"),
        (OperationalError("postgresql://user:password@host/db"), 503, "database unavailable"),
        (QueryCanceled("postgresql://user:password@host/db"), 503, "database unavailable"),
        (ProgrammingError("postgresql://user:password@host/db"), 500, "internal server error"),
        (RuntimeError("postgresql://user:password@host/db"), 500, "internal server error"),
    ],
)
def test_dependency_failures_are_generic_and_logs_exclude_exception_text(
    error: Exception, expected_status: int, expected_detail: str, caplog: pytest.LogCaptureFixture
) -> None:
    repo = FakeRepository()
    repo.error = error
    client = TestClient(build_app(repo))
    with caplog.at_level(logging.INFO):
        response = client.get("/v1/reliability/daily", headers={"X-Request-ID": "safe-id"})
    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert response.headers["X-Request-ID"] == "safe-id"
    assert "postgresql://user:password@host/db" not in caplog.text
    assert str(error) not in caplog.text


def test_openapi_exposes_only_two_data_paths_and_cors_is_disabled() -> None:
    app = build_app(FakeRepository())
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "NetPulse Query API"
    assert schema["info"]["version"] == "1.0.0"
    assert set(schema["paths"]) == {"/healthz", "/v1/reliability/daily"}
    operation = schema["paths"]["/v1/reliability/daily"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert set(parameters) == {
        "from_date",
        "through_date",
        "agent_id",
        "endpoint_id",
        "source_kind",
        "probe_type",
        "limit",
        "cursor",
    }
    assert all(item["in"] == "query" for item in parameters.values())
    for name in ("from_date", "through_date"):
        assert parameters[name]["schema"]["format"] == "date"
    for name in ("agent_id", "endpoint_id", "probe_type"):
        assert parameters[name]["schema"]["minLength"] == 1
        assert parameters[name]["schema"]["maxLength"] == 128
    assert parameters["source_kind"]["schema"]["enum"] == [
        "network_measurement",
        "service_check",
    ]
    assert parameters["limit"]["schema"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 200,
        "default": 50,
    }
    assert parameters["cursor"]["schema"]["maxLength"] == 2048
    assert "422" in operation["responses"]
    assert {route.path for route in app.routes} == {
        "/openapi.json",
        "/docs",
        "/healthz",
        "/v1/reliability/daily",
    }
    assert client.get("/docs").status_code == 200
    response = client.options(
        "/v1/reliability/daily",
        headers={"Origin": "https://other.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers
    assert "X-Request-ID" in response.headers


def test_completion_log_has_only_safe_structured_fields(caplog: pytest.LogCaptureFixture) -> None:
    repo = FakeRepository(ReliabilityPage(rows=(_row(),), has_more=False))
    logger = logging.getLogger("netpulse_query_api")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="netpulse_query_api"):
            response = TestClient(build_app(repo)).get(
                "/v1/reliability/daily?agent_id=agent-a", headers={"X-Request-ID": "trace-1"}
            )
    finally:
        logger.removeHandler(caplog.handler)
    assert response.status_code == 200
    record = next(record for record in caplog.records if record.name == "netpulse_query_api")
    payload = json.loads(record.getMessage())
    assert set(payload) == {
        "event",
        "request_id",
        "route_template",
        "status",
        "elapsed_ms",
        "row_count",
    }
    assert payload["event"] == "request_complete"
    assert payload["request_id"] == "trace-1"
    assert payload["route_template"] == "/v1/reliability/daily"
    assert payload["status"] == 200
    assert payload["row_count"] == 1
    assert payload["elapsed_ms"] >= 0
    assert "agent-a" not in record.getMessage()
