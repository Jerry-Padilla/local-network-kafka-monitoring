from __future__ import annotations

import json
from urllib.request import Request

from netpulse_analytics.orchestration.notification import send_failure_notification


def test_failure_notification_sends_only_safe_fields_without_exposing_url() -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def open_request(request: Request, *, timeout: float) -> Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    send_failure_notification(
        "https://hooks.example.invalid/private-token",
        dag_id="netpulse_daily_reliability",
        run_id="scheduled__2026-10-09",
        task_id="reconcile_analytics",
        error_type="RuntimeError",
        opener=open_request,
    )

    request = captured["request"]
    assert isinstance(request, Request)
    assert captured["timeout"] == 5.0
    assert json.loads(request.data or b"") == {
        "dag_id": "netpulse_daily_reliability",
        "error_type": "RuntimeError",
        "event": "netpulse_airflow_failure",
        "run_id": "scheduled__2026-10-09",
        "task_id": "reconcile_analytics",
    }
    assert b"private-token" not in (request.data or b"")


def test_empty_webhook_configuration_is_a_noop() -> None:
    called = False

    def open_request(_request: Request, *, timeout: float) -> None:
        nonlocal called
        called = True

    send_failure_notification(
        "",
        dag_id="dag",
        run_id="run",
        task_id="task",
        error_type="RuntimeError",
        opener=open_request,
    )

    assert not called
