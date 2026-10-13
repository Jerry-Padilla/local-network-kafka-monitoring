"""Cross-platform operator workflows for NetPulse's optional Airflow profile."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from subprocess import CompletedProcess

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml")]
AIRFLOW = [*COMPOSE, "--profile", "airflow"]
VERIFICATION_DATE = "2035-01-15"
# Keep the DAG run inside its valid historical schedule. The fixture's data
# window is intentionally independent and remains fixed for repeatable checks.
VERIFICATION_LOGICAL_DATE = "2026-01-02T02:00:00Z"
Run = Callable[..., CompletedProcess[str]]


def _run(command: list[str], *, capture_output: bool = False) -> CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def initialize(*, run: Run = _run) -> None:
    run(
        [
            *AIRFLOW,
            "build",
            "migrate",
            "airflow-init",
            "airflow-scheduler",
            "airflow-dag-processor",
            "airflow-api-server",
            "airflow-fixture",
        ]
    )
    run(
        [
            *AIRFLOW,
            "up",
            "--abort-on-container-exit",
            "--exit-code-from",
            "airflow-init",
            "airflow-init",
        ]
    )


def start(*, run: Run = _run) -> None:
    initialize(run=run)
    run(
        [
            *AIRFLOW,
            "up",
            "-d",
            "--wait",
            "airflow-scheduler",
            "airflow-dag-processor",
            "airflow-api-server",
        ]
    )


def test_dag(*, run: Run = _run) -> None:
    start(run=run)
    completed = run(
        [
            *AIRFLOW,
            "exec",
            "-T",
            "airflow-scheduler",
            "airflow",
            "dags",
            "list-import-errors",
            "--output",
            "json",
        ],
        capture_output=True,
    )
    import_errors = json.loads(completed.stdout or "[]")
    if import_errors:
        raise RuntimeError(f"Airflow DAG import errors: {import_errors}")


def verify(*, run: Run = _run) -> None:
    test_dag(run=run)
    run([*AIRFLOW, "run", "--rm", "airflow-fixture"])
    run(
        [
            *AIRFLOW,
            "exec",
            "-T",
            "airflow-scheduler",
            "python",
            "/opt/netpulse/scripts/wait_for_airflow_source.py",
            "--date",
            VERIFICATION_DATE,
            "--timeout",
            "60",
        ]
    )
    configuration = json.dumps(
        {"from_date": VERIFICATION_DATE, "through_date": VERIFICATION_DATE},
        separators=(",", ":"),
    )
    dag_test = [
        *AIRFLOW,
        "exec",
        "-T",
        "airflow-scheduler",
        "airflow",
        "dags",
        "test",
        "netpulse_daily_reliability",
        VERIFICATION_LOGICAL_DATE,
        "--conf",
        configuration,
    ]
    run(dag_test)
    run(dag_test)
    run(
        [
            *AIRFLOW,
            "exec",
            "-T",
            "airflow-scheduler",
            "python",
            "/opt/netpulse/scripts/verify_airflow.py",
            "--from-date",
            VERIFICATION_DATE,
            "--through-date",
            VERIFICATION_DATE,
            "--minimum-attempts=2",
        ]
    )


def down(*, run: Run = _run) -> None:
    services = [
        "airflow-scheduler",
        "airflow-dag-processor",
        "airflow-api-server",
        "airflow-init",
        "airflow-netpulse-init",
        "airflow-postgres",
    ]
    run([*AIRFLOW, "stop", *services])
    run([*AIRFLOW, "rm", "-f", *services])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("airflow-init", "airflow-up", "airflow-test", "airflow-verify", "airflow-down"),
    )
    command = parser.parse_args(argv).command
    actions = {
        "airflow-init": initialize,
        "airflow-up": start,
        "airflow-test": test_dag,
        "airflow-verify": verify,
        "airflow-down": down,
    }
    actions[command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
