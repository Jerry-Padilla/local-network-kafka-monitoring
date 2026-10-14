from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _job_section(workflow: str, job: str, next_job: str | None = None) -> str:
    section = workflow.split(f"  {job}:\n", maxsplit=1)[1]
    if next_job is not None:
        section = section.split(f"  {next_job}:\n", maxsplit=1)[0]
    return section


def test_python313_agent_job_installs_local_observability_package() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert (
        "python -m pip install pytest==8.3.5 ./packages/contracts "
        "./packages/observability ./services/network-agent"
    ) in workflow


def test_local_lint_wrappers_include_ci_format_check() -> None:
    powershell = (ROOT / "scripts" / "netpulse.ps1").read_text(encoding="utf-8")
    posix = (ROOT / "scripts" / "netpulse.sh").read_text(encoding="utf-8")

    powershell_lint = powershell.split('"lint" {', maxsplit=1)[1].split('"format" {', maxsplit=1)[0]
    posix_lint = posix.split("  lint)", maxsplit=1)[1].split("  format)", maxsplit=1)[0]

    assert '"format", "--check", "."' in powershell_lint
    assert "ruff tests format --check ." in posix_lint


def test_quality_job_invokes_pytest_as_a_python_module() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert 'python -m pytest -m "not integration" --cov --cov-report=xml' in workflow


def test_python313_agent_job_excludes_cross_service_schema_test() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "--ignore=packages/contracts/tests/test_json_schemas.py" in workflow


def test_ci_uses_node24_actions_and_a_stable_runner_image() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" not in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "actions/checkout@v5" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "actions/setup-java@v5" in workflow


def test_ci_lints_github_workflows_and_shell_scripts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    containers = _job_section(workflow, "containers", "integration")

    assert "rhysd/actionlint:1.7.12@sha256:" in containers
    assert "koalaman/shellcheck:v0.11.0@sha256:" in containers


def test_ci_runs_live_airflow_acceptance() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    airflow = _job_section(workflow, "airflow-integration", "observability-integration")

    assert "./scripts/netpulse.sh airflow-verify" in airflow


def test_ci_runs_tableau_export_and_checks_the_published_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    analytics = _job_section(workflow, "analytics-integration", "query-api-integration")

    assert "./scripts/netpulse.sh tableau-export" in analytics
    assert "scripts/verify_tableau_export.py tableau_exports" in analytics


def test_ci_runs_live_observability_acceptance() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    observability = _job_section(workflow, "observability-integration")

    assert "./scripts/netpulse.sh monitoring-up" in observability
    assert "./scripts/netpulse.sh monitoring-verify" in observability


def test_container_tests_isolate_bytecode_from_host_caches() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["tests"]["environment"]["PYTHONPYCACHEPREFIX"] == (
        "/tmp/netpulse-pycache"
    )
