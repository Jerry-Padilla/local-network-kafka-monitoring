from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pi_target_renderer_accepts_one_private_host_and_writes_atomically(tmp_path) -> None:
    renderer = _load("render_pi_metrics_target")
    output = tmp_path / "pi-targets.json"

    renderer.render("192.168.1.42", output)
    assert json.loads(output.read_text(encoding="utf-8")) == [
        {
            "targets": ["192.168.1.42:9102"],
            "labels": {"agent": "raspberry-pi", "required": "true"},
        }
    ]
    renderer.render("netpulse-pi.local", output)
    assert json.loads(output.read_text(encoding="utf-8"))[0]["targets"] == [
        "netpulse-pi.local:9102"
    ]


@pytest.mark.parametrize(
    "target",
    [
        "http://192.168.1.42",
        "192.168.1.42:9102",
        "0.0.0.0",
        "8.8.8.8",
        "*",
        "pi host",
        "-bad.local",
    ],
)
def test_pi_target_renderer_rejects_unsafe_or_ambiguous_input(tmp_path, target) -> None:
    renderer = _load("render_pi_metrics_target")
    with pytest.raises(ValueError):
        renderer.render(target, tmp_path / "pi-targets.json")


def test_observability_verifier_checks_targets_datasources_alerts_and_sql() -> None:
    verifier = _load("verify_observability")
    calls: list[str] = []

    def get_json(url: str, **_kwargs):
        calls.append(url)
        if url.endswith("/api/v1/targets"):
            return {"status": "success", "data": {"activeTargets": [{"health": "up"}]}}
        if url.endswith("/api/datasources"):
            return [{"uid": "prometheus"}, {"uid": "postgres"}]
        if url.endswith("/api/v2/status"):
            return {"cluster": {"status": "ready"}}
        raise AssertionError(url)

    sql: list[str] = []
    result = verifier.verify(
        get_json=get_json,
        query_sql=lambda statement: sql.append(statement) or 1,
        grafana_auth=("admin", "secret"),
    )

    assert result == {"targets": 1, "datasources": 2, "alerts_api": "ready", "sql": 1}
    assert any(url.endswith("/api/v1/targets") for url in calls)
    assert sql == ["SELECT count(*) FROM v_sre_pipeline_status"]


def test_failure_drill_always_restores_stopped_dependency() -> None:
    drills = _load("failure_drills")
    commands: list[tuple[str, ...]] = []

    def run(*args: str) -> None:
        commands.append(args)
        if args[0] == "observe":
            raise RuntimeError("verification failed")

    with pytest.raises(RuntimeError):
        drills.dependency_outage("kafka", run=run, observe=lambda: run("observe"), settle_seconds=0)

    assert commands[0] == ("docker", "compose", "stop", "kafka")
    assert commands[-1] == ("docker", "compose", "start", "kafka")


def test_operator_entrypoints_expose_equivalent_monitoring_commands() -> None:
    expected = {
        "monitoring-render",
        "monitoring-up",
        "monitoring-verify",
        "monitoring-down",
        "failure-drill",
    }
    for relative in ("scripts/netpulse.ps1", "scripts/netpulse.sh", "Makefile"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert expected <= {command for command in expected if command in text}
