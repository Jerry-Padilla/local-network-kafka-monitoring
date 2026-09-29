#!/usr/bin/env python3
"""Perform read-only checks against the local observability plane."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _get_json(url: str, *, auth: tuple[str, str] | None = None) -> Any:
    request = urllib.request.Request(url)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def _query_sql(statement: str) -> int:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "netpulse_admin",
            "-d",
            os.getenv("POSTGRES_DB", "netpulse"),
            "-Atc",
            statement,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def verify(
    *,
    get_json: Callable[..., Any] = _get_json,
    query_sql: Callable[[str], int] = _query_sql,
    grafana_auth: tuple[str, str] | None = None,
) -> dict[str, Any]:
    targets = get_json("http://127.0.0.1:9090/api/v1/targets")["data"]["activeTargets"]
    unhealthy = [
        target
        for target in targets
        if target.get("labels", {}).get("required") == "true" and target.get("health") != "up"
    ]
    if unhealthy:
        raise RuntimeError(f"Prometheus has {len(unhealthy)} unhealthy active targets")
    datasources = get_json("http://127.0.0.1:3000/api/datasources", auth=grafana_auth)
    uids = {item["uid"] for item in datasources}
    if not {"prometheus", "postgres"} <= uids:
        raise RuntimeError("Grafana is missing a required provisioned datasource")
    dashboards = get_json("http://127.0.0.1:3000/api/search?tag=netpulse", auth=grafana_auth)
    if len({item.get("uid") for item in dashboards}) < 3:
        raise RuntimeError("Grafana is missing one or more NetPulse dashboards")
    rule_groups = get_json("http://127.0.0.1:9090/api/v1/rules")["data"]["groups"]
    if not rule_groups or any(
        rule.get("health") != "ok" for group in rule_groups for rule in group.get("rules", [])
    ):
        raise RuntimeError("Prometheus rules are absent or unhealthy")
    alert_status = get_json("http://127.0.0.1:9093/api/v2/status")
    ready = alert_status.get("cluster", {}).get("status")
    if ready not in {"ready", "disabled"}:
        raise RuntimeError("Alertmanager is not ready")
    sql = query_sql("SELECT count(*) FROM v_sre_agent_status")
    if sql < 1:
        raise RuntimeError("SRE reporting views contain no registered agents")
    return {
        "targets": len(targets),
        "datasources": len(datasources),
        "dashboards": len(dashboards),
        "rule_groups": len(rule_groups),
        "alerts_api": ready,
        "sql": sql,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-user", default=os.getenv("GRAFANA_ADMIN_USER", "admin"))
    password = os.getenv("GRAFANA_ADMIN_PASSWORD")
    env_file = ROOT / ".env"
    if not password and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GRAFANA_ADMIN_PASSWORD="):
                password = line.partition("=")[2]
                break
    parser.add_argument("--grafana-password", default=password)
    args = parser.parse_args()
    if not args.grafana_password:
        parser.error("set GRAFANA_ADMIN_PASSWORD or pass --grafana-password")
    print(json.dumps(verify(grafana_auth=(args.grafana_user, args.grafana_password)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
