from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
