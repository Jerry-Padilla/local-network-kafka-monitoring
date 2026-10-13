"""Best-effort failure notifications without provider-specific dependencies."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen


def send_failure_notification(
    webhook_url: str,
    *,
    dag_id: str,
    run_id: str,
    task_id: str,
    error_type: str,
    opener: Callable[..., Any] = urlopen,
) -> None:
    if not webhook_url:
        return
    payload = json.dumps(
        {
            "dag_id": dag_id,
            "error_type": error_type,
            "event": "netpulse_airflow_failure",
            "run_id": run_id,
            "task_id": task_id,
        },
        sort_keys=True,
    ).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener(request, timeout=5.0):
        pass
