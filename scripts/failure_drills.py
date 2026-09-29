#!/usr/bin/env python3
"""Run reversible drills, prove expected alerts, and wait for recovery."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

COMPOSE = (
    "docker",
    "compose",
    "-f",
    str(Path(__file__).resolve().parents[1] / "docker-compose.yml"),
)


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _alerts() -> list[dict]:
    with urllib.request.urlopen("http://127.0.0.1:9090/api/v1/alerts", timeout=10) as response:
        return json.load(response)["data"]["alerts"]


def _wait_for_alert(
    name: str,
    *,
    firing: bool,
    observe: Callable[[], list[dict]] = _alerts,
    timeout_seconds: float,
    interval_seconds: float = 5,
) -> list[dict]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        alerts = observe()
        active = any(
            item.get("labels", {}).get("alertname") == name
            and item.get("state") in {"pending", "firing"}
            for item in alerts
        )
        if active is firing:
            return alerts
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{name} did not {'fire' if firing else 'resolve'} within {timeout_seconds}s"
            )
        time.sleep(interval_seconds)


def dependency_outage(
    service: str,
    *,
    run: Callable[..., None] = _run,
    observe: Callable[[], list[dict]] = _alerts,
    alert_name: str | None = None,
    fire_timeout: float = 360,
    recovery_timeout: float = 180,
) -> dict[str, object]:
    expected = alert_name or (
        "NetPulsePostgresUnavailable" if service == "postgres" else "NetPulseKafkaUnavailable"
    )
    started = datetime.now(UTC).isoformat()
    run(*COMPOSE, "stop", service)
    try:
        fired = _wait_for_alert(
            expected, firing=True, observe=observe, timeout_seconds=fire_timeout
        )
        fired_at = datetime.now(UTC).isoformat()
    finally:
        run(*COMPOSE, "start", service)
    resolved = _wait_for_alert(
        expected, firing=False, observe=observe, timeout_seconds=recovery_timeout
    )
    return {
        "drill": f"{service}-outage",
        "started_at": started,
        "fired_at": fired_at,
        "fired": fired,
        "resolved": resolved,
        "recovered_at": datetime.now(UTC).isoformat(),
    }


def malformed_traffic(
    *, run: Callable[..., None] = _run, observe: Callable[[], list[dict]] = _alerts
) -> dict[str, object]:
    run(
        *COMPOSE,
        "--profile",
        "demo",
        "run",
        "--rm",
        "simulator",
        "run",
        "--scenario",
        "malformed-events",
        "--duration",
        "2",
    )
    fired = _wait_for_alert(
        "NetPulseDeadLetterGrowth", firing=True, observe=observe, timeout_seconds=60
    )
    return {
        "drill": "malformed-traffic",
        "fired": fired,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def traffic_pause(
    *, run: Callable[..., None] = _run, observe: Callable[[], list[dict]] = _alerts
) -> dict[str, object]:
    container = "netpulse-traffic-drill"
    run(
        *COMPOSE,
        "--profile",
        "demo",
        "run",
        "-d",
        "--name",
        container,
        "simulator",
        "run",
        "--scenario",
        "healthy",
        "--duration",
        "600",
    )
    try:
        time.sleep(30)
        run("docker", "stop", container)
        fired = _wait_for_alert(
            "NetPulsePipelineStale", firing=True, observe=observe, timeout_seconds=240
        )
    finally:
        run("docker", "rm", "-f", container)
    return {"drill": "traffic-pause", "fired": fired, "recorded_at": datetime.now(UTC).isoformat()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "drill",
        choices=("kafka", "postgres", "malformed", "traffic-pause", "all"),
        default="all",
        nargs="?",
    )
    args = parser.parse_args()
    selected = (
        ("kafka", "postgres", "malformed", "traffic-pause")
        if args.drill == "all"
        else (args.drill,)
    )
    results = []
    for drill in selected:
        results.append(
            dependency_outage(drill)
            if drill in {"kafka", "postgres"}
            else malformed_traffic()
            if drill == "malformed"
            else traffic_pause()
        )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
