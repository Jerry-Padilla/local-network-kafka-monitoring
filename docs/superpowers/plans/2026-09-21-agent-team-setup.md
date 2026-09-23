# NetPulse Agent Team Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define three reusable, project-scoped Codex development helpers with explicit ownership, model preferences, and a read-only verification boundary.

**Architecture:** Keep the three role definitions in separate `.codex/agents/*.toml` files and a concurrency limit in `.codex/config.toml`. Document invocation and handoff rules in `docs/agent-team.md`; check structure with a stdlib `tomllib` test so the repository detects accidental config drift.

**Tech Stack:** Codex project configuration (TOML), Python 3.12 stdlib `tomllib`, Pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-agent-team-and-remaining-roadmap-design.md`

## Global Constraints

- The lead owns architecture, integration, user status, and final checks; helpers work only on bounded tasks.
- Use the current model preferences: `gpt-5.6-sol`/medium for data, `gpt-5.6-terra`/medium for platform/Pi, and `gpt-5.6-terra`/high for verifier.
- Cap concurrent helpers at three and preserve read-only access for the verifier.
- Helpers do not commit, push, deploy, change firewall settings, or claim physical Pi evidence without specific user authorization. The lead performs any local commits after review.
- These are Codex development helpers, not runtime telemetry producers.

## Review Focus

- A role file missing a required `name`, `description`, or `developer_instructions` must fail the configuration test.
- Duplicate role names must fail, or Codex could resolve the wrong worker.
- A verifier configured for writing must fail, preserving review independence.
- A concurrency limit above three must fail, matching the agreed team budget.
- A model or reasoning-effort typo must fail, so runtime configuration drift is visible.

---

### Task 1: Guard the project agent configuration

**Files:**
- Create: `tests/test_agent_configuration.py`
- Create: `.codex/config.toml`
- Create: `.codex/agents/data_engineer.toml`
- Create: `.codex/agents/platform_pi_engineer.toml`
- Create: `.codex/agents/verifier.toml`

**Interfaces:**
- Consumes: Codex's required custom-agent fields `name`, `description`, `developer_instructions` and optional `model`, `model_reasoning_effort`, `sandbox_mode`.
- Produces: three distinct project-scoped role names and `[agents].max_concurrent_threads_per_session = 3`.

- [ ] **Step 1: Write the failing configuration test** in `tests/test_agent_configuration.py`:

```python
from pathlib import Path
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROLES = {
    "data_engineer": ("gpt-5.6-sol", "medium"),
    "platform_pi_engineer": ("gpt-5.6-terra", "medium"),
    "verifier": ("gpt-5.6-terra", "high"),
}


def read_toml(relative_path: str) -> dict[str, object]:
    return tomllib.loads((ROOT / relative_path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,expected", ROLES.items())
def test_agent_role(name: str, expected: tuple[str, str]) -> None:
    config = read_toml(f".codex/agents/{name}.toml")
    assert config["name"] == name
    assert all(isinstance(config[key], str) and config[key].strip()
               for key in ("name", "description", "developer_instructions"))
    assert (config["model"], config["model_reasoning_effort"]) == expected
    if name == "verifier":
        assert config["sandbox_mode"] == "read-only"


def test_role_names_are_unique() -> None:
    role_files = sorted((ROOT / ".codex/agents").glob("*.toml"))
    assert {path.stem for path in role_files} == set(ROLES)
    names = [tomllib.loads(path.read_text(encoding="utf-8"))["name"]
             for path in role_files]
    assert len(set(names)) == len(ROLES)


def test_concurrency_limit() -> None:
    config = read_toml(".codex/config.toml")
    assert config["agents"]["max_concurrent_threads_per_session"] == 3
```
- [ ] **Step 2: Run `python -m pytest tests/test_agent_configuration.py -q`.** In the inspected baseline, the role files are absent, so the test should fail for missing files. If files have appeared meanwhile, verify the test fails for an intentional temporary defect before accepting it as a regression guard.
- [ ] **Step 3: Add the four TOML files** with this exact content (each block goes in its named file):

`.codex/config.toml`:

```toml
[agents]
max_concurrent_threads_per_session = 3
```

`.codex/agents/data_engineer.toml`:

```toml
name = "data_engineer"
description = "Builds NetPulse analytics models, replay-safe batch ETL, and read-only data contracts."
model = "gpt-5.6-sol"
model_reasoning_effort = "medium"
developer_instructions = """
Own only the data paths named in the parent's task brief. Preserve event-time
semantics and at-least-once deduplication. State fact grain, keys, and source
tables. Add tests for replay and late data. Report exact commands and results.
Do not commit, push, deploy, or change the Pi or firewall without explicit
user authorization. Do not approve your own work.
"""
```

`.codex/agents/platform_pi_engineer.toml`:

```toml
name = "platform_pi_engineer"
description = "Handles Pi 3 B+ compatibility and reproducible local deployment."
model = "gpt-5.6-terra"
model_reasoning_effort = "medium"
developer_instructions = """
Own only the platform paths named in the parent's task brief. Verify actual
Pi hardware and OS versions before claiming compatibility. Keep secrets out
of Git and do not open LAN listeners or alter firewall settings without
explicit user authorization. Report exact commands and observed results.
Do not commit, push, or deploy without explicit user authorization.
"""
```

`.codex/agents/verifier.toml`:

```toml
name = "verifier"
description = "Independently reviews NetPulse correctness, security, tests, and claims."
model = "gpt-5.6-terra"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
developer_instructions = """
Review the task brief and actual diff independently. Prioritize correctness,
replay and failure semantics, migration safety, security/privacy, and missing
tests. Cite exact paths and evidence, distinguish observed from unverified,
and return findings by severity. Never edit files, commit, push, deploy,
or mark a phase complete.
"""
```
- [ ] **Step 4: Run `python -m pytest tests/test_agent_configuration.py -q` and `python -m pytest -q`.** Both must pass before a completion claim.
- [ ] **Step 5: Review `git diff --check` and the five TOML/test files.** Return the diff and exact checks to the lead; the helper must not commit. After independent review, the lead may commit only these paths with `git commit -m "chore: define NetPulse Codex helper roles"`.

### Task 2: Make delegation and handoffs usable

**Files:**
- Create: `docs/agent-team.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: names and boundaries from Task 1 and the design spec.
- Produces: a task-brief template naming deliverable, owned paths, dependencies, exact acceptance commands, and prohibitions; a review template naming findings, evidence, and unresolved risk.

- [ ] **Step 1: Add `docs/agent-team.md`** with the following sections: `Purpose`, `Roles`, `Task brief`, `Review brief`, and `Acceptance`. In `Task brief`, provide this copyable form: `Role: ...; Deliverable: ...; Owned paths: ...; Dependencies: ...; Acceptance commands: ...; Prohibitions: no commit/push/deploy/network changes unless authorized.` In `Review brief`, request findings with severity, path, evidence, reproduction, and unresolved risk. State that helpers are spawned per task, may require a new Codex session to load, do not run on the Pi, and never replace lead verification. In `Acceptance`, instruct the lead to verify in a fresh Codex session that all three roles are discoverable/spawnable and to check the verifier's effective permissions: parent live sandbox/approval overrides can supersede a custom agent file's read-only default, so TOML parsing alone is not proof of a read-only runtime.
- [ ] **Step 2: Link the guide from `README.md` and add a short `AGENTS.md` section routing data, platform, and independent review tasks.** Do not alter the runtime service map or imply Phase 5 is complete.
- [ ] **Step 3: Run `git diff --check`, `python -m pytest tests/test_agent_configuration.py -q`, and `python -m pytest -q`.** Record exact outputs and any environmental skips.
- [ ] **Step 4: Check the guide against the design spec and current role TOML.** Return the diff to the lead; the helper must not commit. After independent review, the lead may commit only these documentation paths with `git commit -m "docs: explain NetPulse agent handoffs"`.

## Self-review

This plan covers all three roles, concurrency, the intended read-only verifier default, operating instructions, and checks from the design. Runtime read-only enforcement requires fresh-session observation because parent live permission overrides may take precedence. It intentionally does not implement Phase 5A data processing, flash the Pi card, or claim that these custom roles are loaded into the current conversation. Those are separate acceptance paths.
