from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    def __init__(self, import_errors: list[object] | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.import_errors = import_errors or []

    def __call__(
        self, command: list[str], *, capture_output: bool = False
    ) -> CompletedProcess[str]:
        self.commands.append(tuple(command))
        output = json.dumps(self.import_errors) if "list-import-errors" in command else ""
        return CompletedProcess(command, 0, output if capture_output else "", "")


def test_airflow_init_builds_current_migration_and_runtime_images() -> None:
    workflows = _load_script("airflow_workflows")
    recorder = Recorder()

    workflows.initialize(run=recorder)

    assert recorder.commands[0][-7:] == (
        "build",
        "migrate",
        "airflow-init",
        "airflow-scheduler",
        "airflow-dag-processor",
        "airflow-api-server",
        "airflow-fixture",
    )
    assert recorder.commands[1][-5:] == (
        "up",
        "--abort-on-container-exit",
        "--exit-code-from",
        "airflow-init",
        "airflow-init",
    )


def test_airflow_test_starts_healthy_runtime_and_rejects_import_errors() -> None:
    workflows = _load_script("airflow_workflows")
    recorder = Recorder()

    workflows.test_dag(run=recorder)

    assert any(
        command[-6:]
        == (
            "up",
            "-d",
            "--wait",
            "airflow-scheduler",
            "airflow-dag-processor",
            "airflow-api-server",
        )
        for command in recorder.commands
    )
    assert recorder.commands[-1][-5:] == (
        "airflow",
        "dags",
        "list-import-errors",
        "--output",
        "json",
    )

    failing = Recorder([{"filename": "broken.py", "stack_trace": "boom"}])
    try:
        workflows.test_dag(run=failing)
    except RuntimeError as error:
        assert "import errors" in str(error)
    else:
        raise AssertionError("DAG import errors must fail the workflow")


def test_airflow_verify_uses_fixed_simulator_window_and_reruns_same_dag() -> None:
    workflows = _load_script("airflow_workflows")
    recorder = Recorder()

    workflows.verify(run=recorder)

    fixture = next(
        command
        for command in recorder.commands
        if command[-3:] == ("run", "--rm", "airflow-fixture")
    )
    assert fixture[-3:] == ("run", "--rm", "airflow-fixture")
    dag_tests = [
        command for command in recorder.commands if "dags" in command and "test" in command
    ]
    assert len(dag_tests) == 2
    assert dag_tests[0] == dag_tests[1]
    assert workflows.VERIFICATION_LOGICAL_DATE in dag_tests[0]
    assert workflows.VERIFICATION_LOGICAL_DATE == "2026-01-02T02:00:00Z"
    wait = next(
        command
        for command in recorder.commands
        if "/opt/netpulse/scripts/wait_for_airflow_source.py" in command
    )
    assert wait[-4:] == ("--date", workflows.VERIFICATION_DATE, "--timeout", "60")
    verifier = recorder.commands[-1]
    assert verifier[-6:] == (
        "/opt/netpulse/scripts/verify_airflow.py",
        "--from-date",
        workflows.VERIFICATION_DATE,
        "--through-date",
        workflows.VERIFICATION_DATE,
        "--minimum-attempts=2",
    )


def test_operator_entrypoints_delegate_all_airflow_commands() -> None:
    expected = {
        "airflow-init",
        "airflow-up",
        "airflow-test",
        "airflow-verify",
        "airflow-down",
    }
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    bash = (ROOT / "scripts/netpulse.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "scripts/netpulse.ps1").read_text(encoding="utf-8")

    assert expected <= set(makefile.split())
    assert all(command in bash for command in expected)
    assert all(f'"{command}"' in powershell for command in expected)
    assert "scripts/airflow_workflows.py" in makefile
