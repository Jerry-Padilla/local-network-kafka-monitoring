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


def test_analytics_commands_create_tableau_bind_mount_before_docker_runs() -> None:
    bash = (ROOT / "scripts" / "netpulse.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "scripts" / "netpulse.ps1").read_text(encoding="utf-8")

    for command, next_command in (
        ("analytics-all", "analytics-verify"),
        ("analytics-verify", "tableau-export"),
    ):
        bash_block = bash.split(f"  {command})", maxsplit=1)[1].split(
            f"  {next_command})", maxsplit=1
        )[0]
        assert bash_block.index('mkdir -p "$repository_root/tableau_exports"') < bash_block.index(
            '"${compose[@]}"'
        )

        powershell_block = powershell.split(f'    "{command}" {{', maxsplit=1)[1].split(
            f'    "{next_command}" {{', maxsplit=1
        )[0]
        assert powershell_block.index("New-Item -ItemType Directory") < powershell_block.index(
            "Invoke-DockerCompose"
        )
