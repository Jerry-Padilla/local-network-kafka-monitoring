from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_workflow(path: Path) -> dict[str, Any]:
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(document, dict)
    return document


def test_codeql_scans_python_changes_and_on_a_weekly_schedule() -> None:
    workflow = _load_workflow(ROOT / ".github" / "workflows" / "codeql.yml")

    triggers = workflow["on"]
    assert triggers["push"]["branches"] == ["master"]
    assert triggers["pull_request"]["branches"] == ["master"]
    assert triggers["schedule"] == [{"cron": "17 12 * * 1"}]
    assert "workflow_dispatch" in triggers

    analyze = workflow["jobs"]["analyze"]
    assert analyze["runs-on"] == "ubuntu-24.04"
    assert analyze["permissions"] == {
        "contents": "read",
        "packages": "read",
        "security-events": "write",
    }

    action_steps = [step for step in analyze["steps"] if "uses" in step]
    assert action_steps == [
        {"name": "Check out repository", "uses": "actions/checkout@v7"},
        {
            "name": "Initialize CodeQL",
            "uses": "github/codeql-action/init@v4",
            "with": {"languages": "python", "queries": "security-extended"},
        },
        {"name": "Analyze", "uses": "github/codeql-action/analyze@v4"},
    ]


def test_dependabot_covers_python_monorepo_and_github_actions() -> None:
    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))

    assert config["version"] == 2
    updates = {entry["package-ecosystem"]: entry for entry in config["updates"]}
    assert set(updates) == {"pip", "github-actions"}

    pip = updates["pip"]
    assert pip["directories"] == ["/", "/packages/*", "/services/*"]
    assert pip["schedule"]["interval"] == "weekly"
    assert pip["groups"]["python-dependencies"] == {
        "patterns": ["*"],
        "group-by": "dependency-name",
        "update-types": ["minor", "patch"],
    }
    assert {entry["dependency-name"] for entry in pip["ignore"]} == {"netpulse-*"}

    actions = updates["github-actions"]
    assert actions["directory"] == "/"
    assert actions["schedule"]["interval"] == "weekly"
    assert actions["groups"]["github-actions"] == {
        "patterns": ["*"],
        "update-types": ["minor", "patch"],
    }
