# Codex development agent team

## Purpose

These are project-scoped Codex helpers for developing NetPulse. They are not
the simulator's two telemetry identities or the Raspberry Pi network agent.
The lead conversation owns architecture, integration, final verification, and
status reported to the user. Helpers are spawned for bounded tasks; they do
not run continuously and they do not run on the Pi.

## Roles

| Role | Use for | Boundary |
| --- | --- | --- |
| `data_engineer` | Analytics grain, migrations, replay-safe ETL, and data contracts | No Pi or firewall changes; cannot approve its own work |
| `platform_pi_engineer` | Pi 3 B+ compatibility and local deployment | No invented hardware evidence, LAN listener, or firewall change |
| `verifier` | Independent correctness, security, and test review | Read-only default; never edits or marks a phase complete |

Role definitions are in `.codex/agents/`; `.codex/config.toml` caps concurrent
helpers at three. Spawn only roles whose work is independent, with explicit
file ownership. No helper commits, pushes, deploys, or changes network exposure
without specific user authorization. The lead reviews and integrates results.

## Task brief

Copy this into the lead's delegation message:

```text
Role: data_engineer | platform_pi_engineer | verifier
Deliverable: <bounded outcome>
Owned paths: <exact files or directories>
Dependencies: <inputs and predecessor work>
Acceptance commands: <exact tests or read-only checks to run>
Prohibitions: no commit/push/deploy/network changes unless authorized;
  no claims of physical Pi validation without device evidence.
```

An implementation helper returns changed paths, exact commands and outcomes,
unverified assumptions, and any security or privacy implications. The lead
retains responsibility for review, integration, and final checks.

## Review brief

Ask the verifier to inspect the task brief and actual diff independently.
Findings should give severity, file and line, evidence, reproduction steps
when feasible, and unresolved risk. It should distinguish observations from
inferences and report when a check was unavailable. The verifier does not
modify files or turn its opinion into an acceptance claim.

## Acceptance

Run `python -m pytest tests/test_agent_configuration.py -q` to check the
project TOML structure. In a **new Codex session** opened from this trusted
repository, confirm all three custom roles are discoverable and can be
spawned. Also inspect the verifier's effective runtime permissions: a parent
session's live sandbox or approval settings may supersede its `read-only`
default, so parsing TOML alone does not prove read-only enforcement. Do not
claim the roles are loaded into this existing conversation solely because
their files exist.

## Resuming this project

Open the original repository (`Data Engineering Project`) when resuming work;
the separate `ChatGPT/Netpulse` folder does not contain these project roles.
Keep the models and concurrency cap in the project TOML files unchanged.

Some session tool interfaces offer generic helper spawning without a named-role
or sandbox selector. In that case the lead can pass each role's instructions,
model, and reasoning effort explicitly, but must report this as an explicit
role handoff rather than automatic TOML loading. Inspect effective permissions
before a verifier review; a written no-edit instruction is not an OS sandbox.
Do not request elevated commands for a verifier. Fresh-session named-role
loading remains a separate check when the runtime supports it.