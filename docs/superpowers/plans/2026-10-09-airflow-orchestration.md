# Apache Airflow Orchestration Implementation Plan

> Execute test-first, commit each completed task, and keep Airflow optional.

**Goal:** Add a real, replay-safe daily analytics DAG with source validation,
reconciliation, operational state, and a lightweight local deployment.

**Architecture:** Reusable typed orchestration logic belongs in
`services/analytics`; the DAG is a thin dependency graph. Airflow 3.3.2 uses
LocalExecutor and a separate PostgreSQL metadata service under the `airflow` profile.

## Task 1: Date windows and source-quality contracts

- Add `netpulse_analytics.orchestration.models` and `selection`.
- Test scheduled previous-day selection, explicit inclusive overrides, invalid and
  over-31-day ranges, and UTC awareness.
- Add typed source snapshot/status classification with tests for healthy, delayed,
  empty, missing, stale, and invalid windows.

## Task 2: Reusable reconciliation and validation

- Add a PostgreSQL orchestration repository with read-only source inspection,
  bounded fact reconciliation, incident reconciliation, and reporting validation.
- Extract the existing verifier's definitions into reusable analytics code and keep
  `scripts/verify_analytics.py` behavior compatible.
- Test SQL boundaries, mismatch propagation, empty ranges, and connection failures.

## Task 3: Idempotent operational run records

- Add migration `0009` for `analytics_orchestration_runs` and
  `v_analytics_workflow_status`.
- Add repository start/success/failure upserts and tests proving the same run key is
  updated rather than duplicated.
- Grant only the required read/write objects to a dedicated login through an
  idempotent provisioning script; test privilege declarations.

## Task 4: Thin Airflow DAG and notification callback

- Add the pinned custom image and `deployment/airflow/dags/netpulse_daily_reliability.py`.
- Implement the seven-task dependency chain using `airflow.sdk`, explicit timeouts,
  bounded retries, UTC schedule, `max_active_runs=1`, and optional webhook callback.
- Add host-side DAG contract tests and callback unit tests; use the image for actual
  parse/import verification.

## Task 5: Optional Compose infrastructure

- Add metadata PostgreSQL, init, scheduler, DAG processor, and loopback-only API
  server under the `airflow` profile with persistent metadata/log volumes and health
  checks.
- Add `.env.example` configuration without secrets and Compose deployment tests.
- Validate Compose with and without the profile.

## Task 6: Operator workflows and live verifier

- Add `airflow-init`, `airflow-up`, `airflow-test`, `airflow-verify`, and
  `airflow-down` to Make, Bash, and PowerShell surfaces.
- Add a repeatable verifier that checks DAG import, successful run, reconciliation,
  and idempotent rerun state against deterministic simulator data.
- Test command wiring at behavioral boundaries and execute the live workflow.

## Task 7: Existing Grafana integration

- Add a workflow-health panel backed by `v_analytics_workflow_status` to the existing
  pipeline dashboard.
- Extend dashboard/config tests for datasource, query, and neutral no-run behavior.

## Task 8: Documentation and final verification

- Add `docs/airflow-orchestration.md` with architecture, scheduling, configuration,
  operation, recovery, backfill, reconciliation, limitations, and runbook guidance.
- Update README, architecture, analytics, failure-testing, roadmap, CI Compose
  validation, and documentation links.
- Run formatter, lint, mypy, unit suite, Compose checks, Airflow import check, live
  DAG execution twice, reconciliation verification, and a final diff/privacy review.
