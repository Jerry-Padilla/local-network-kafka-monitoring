from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_analytics_service_mounts_only_generated_tableau_output_for_writing() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    analytics = compose["services"]["analytics"]

    assert analytics["profiles"] == ["analytics"]
    assert "ports" not in analytics
    assert analytics["volumes"] == ["./tableau_exports:/exports"]


def test_tableau_exports_are_gitignored() -> None:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "check-ignore",
            "tableau_exports/sample.csv",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "tableau_exports/sample.csv"
