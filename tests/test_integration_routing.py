"""Executable pytest-selection contract for integration environments."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _collect(marker: str) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            marker,
            "tests/integration",
            "tests/test_query_api_integration.py",
            "tests/test_query_api_provisioning_live.py",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_legacy_integration_selection_excludes_api_and_host_only_tests() -> None:
    selected = _collect("integration and not api_integration and not host_integration")

    assert "test_phase1_stack.py" in selected
    assert "test_query_api_integration.py" not in selected
    assert "test_query_api_provisioning_live.py" not in selected


def test_api_and_host_integration_selections_are_disjoint() -> None:
    api_selected = _collect("api_integration")
    host_selected = _collect("host_integration")

    assert "test_query_api_integration.py" in api_selected
    assert "test_query_api_provisioning_live.py" not in api_selected
    assert "test_query_api_provisioning_live.py" in host_selected
    assert "test_query_api_integration.py" not in host_selected
