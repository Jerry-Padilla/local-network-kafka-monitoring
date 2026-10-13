from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_analytics_service_mounts_only_generated_tableau_output_for_writing() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    analytics = compose["services"]["analytics"]

    assert analytics["profiles"] == ["analytics"]
    assert "ports" not in analytics
    assert analytics["volumes"] == ["./tableau_exports:/exports"]


def test_tableau_exports_directory_is_listed_in_gitignore() -> None:
    entries = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "/tableau_exports/" in entries


def test_tableau_export_promotion_does_not_require_host_python() -> None:
    powershell_wrapper = (ROOT / "scripts" / "netpulse.ps1").read_text(encoding="utf-8")

    assert "function Promote-TableauExport" in powershell_wrapper
    assert "Promote-TableauExport $OutputDirectory" in powershell_wrapper
    host_python_call = '& python (Join-Path $RepositoryRoot "scripts/promote_tableau_export.py")'
    assert host_python_call not in powershell_wrapper
