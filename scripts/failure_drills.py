#!/usr/bin/env python3
"""Run reversible local failure drills and always restore stopped dependencies."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _alerts() -> list[dict]:
    with urllib.request.urlopen("http://127.0.0.1:9090/api/v1/alerts", timeout=10) as response:
        return json.load(response)["data"]["alerts"]


def dependency_outage(
    service: str,
    *,
    run: Callable[..., None] = _run,
    observe: Callable[[], object] = _alerts,
    settle_seconds: float = 75,
) -> dict[str, object]:
    started = datetime.now(UTC).isoformat()
    run("docker", "compose", "stop", service)
    try:
        if settle_seconds:
            time.sleep(settle_seconds)
        observed = observe()
    finally:
        run("docker", "compose", "start", service)
    return {
        "drill": f"{service}-outage",
        "started_at": started,
        "observed": observed,
        "restored_at": datetime.now(UTC).isoformat(),
    }


def malformed_traffic(
    *, run: Callable[..., None] = _run, observe: Callable[[], object] = _alerts
) -> dict[str, object]:
    run(
        "docker",
        "compose",
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
    return {
        "drill": "malformed-traffic",
        "observed": observe(),
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def traffic_pause(
    *, run: Callable[..., None] = _run, observe: Callable[[], object] = _alerts
) -> dict[str, object]:
    run("docker", "compose", "stop", "simulator")
    try:
        observed = observe()
    finally:
        run("docker", "compose", "start", "simulator")
    return {
        "drill": "traffic-pause",
        "observed": observed,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


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
        if drill in {"kafka", "postgres"}:
            results.append(dependency_outage(drill))
        elif drill == "malformed":
            results.append(malformed_traffic())
        else:
            results.append(traffic_pause())
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
