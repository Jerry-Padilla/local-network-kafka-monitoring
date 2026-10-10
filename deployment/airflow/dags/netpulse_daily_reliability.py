"""Schedule and validate NetPulse's existing transactional daily analytics job."""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

from airflow.sdk import DAG, Param, get_current_context, task
from netpulse_analytics.cli import DateSelection
from netpulse_analytics.orchestration.dag_contract import DAG_CONTRACT
from netpulse_analytics.orchestration.models import DateRange, ReconciliationResult
from netpulse_analytics.orchestration.notification import send_failure_notification
from netpulse_analytics.orchestration.quality import assess_source_quality
from netpulse_analytics.orchestration.repository import PostgresOrchestrationRepository
from netpulse_analytics.orchestration.selection import select_date_range
from netpulse_analytics.repository import PostgresAnalyticsRepository

LOGGER = logging.getLogger(__name__)


def _database_url() -> str:
    value = os.environ.get("NETPULSE_DATABASE_URL", "").strip()
    if not value:
        raise ValueError("NETPULSE_DATABASE_URL is required")
    return value


def _selected(payload: dict[str, str]) -> DateRange:
    return DateRange(
        date.fromisoformat(payload["from_date"]),
        date.fromisoformat(payload["through_date"]),
    )


def _failure_callback(context: dict[str, Any]) -> None:
    run_id = str(context.get("run_id", "unknown"))
    task_instance = context.get("task_instance")
    task_id = str(getattr(task_instance, "task_id", "unknown"))
    exception = context.get("exception")
    error_type = type(exception).__name__ if exception is not None else "UnknownError"
    try:
        PostgresOrchestrationRepository(_database_url()).record_failure(
            run_id, task_id, error_type
        )
    except Exception:
        LOGGER.exception("failed to record Airflow DAG failure metadata")
    try:
        send_failure_notification(
            os.environ.get("NETPULSE_AIRFLOW_FAILURE_WEBHOOK_URL", ""),
            dag_id=DAG_CONTRACT.dag_id,
            run_id=run_id,
            task_id=task_id,
            error_type=error_type,
        )
    except Exception:
        LOGGER.exception("failed to send configured Airflow failure notification")


with DAG(
    dag_id=DAG_CONTRACT.dag_id,
    description="Validate, refresh, and reconcile NetPulse daily reliability analytics",
    schedule=DAG_CONTRACT.schedule,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=DAG_CONTRACT.catchup,
    max_active_runs=DAG_CONTRACT.max_active_runs,
    dagrun_timeout=DAG_CONTRACT.dag_timeout,
    params={
        "from_date": Param(None, type=["null", "string"], format="date"),
        "through_date": Param(None, type=["null", "string"], format="date"),
    },
    on_failure_callback=_failure_callback,
    tags=["netpulse", "analytics", "data-quality"],
) as dag:

    @task(
        task_id="resolve_date_range",
        execution_timeout=DAG_CONTRACT.task_timeouts["resolve_date_range"],
    )
    def resolve_date_range() -> dict[str, str]:
        context = get_current_context()
        params = context["params"]
        selected = select_date_range(
            context.get("data_interval_end"),
            params.get("from_date"),
            params.get("through_date"),
            maximum_days=DAG_CONTRACT.maximum_backfill_days,
        )
        return {
            "from_date": selected.from_date.isoformat(),
            "through_date": selected.through_date.isoformat(),
        }

    @task(
        task_id="check_postgres",
        retries=DAG_CONTRACT.retries_for("check_postgres"),
        retry_delay=timedelta(minutes=1),
        execution_timeout=DAG_CONTRACT.task_timeouts["check_postgres"],
    )
    def check_postgres(payload: dict[str, str]) -> dict[str, str]:
        PostgresOrchestrationRepository(_database_url()).check_database()
        return payload

    @task(
        task_id="assess_source_quality",
        execution_timeout=DAG_CONTRACT.task_timeouts["assess_source_quality"],
    )
    def assess_source(payload: dict[str, str]) -> dict[str, str]:
        repository = PostgresOrchestrationRepository(_database_url())
        assessment = assess_source_quality(
            repository.load_source_snapshot(_selected(payload)),
            stale_after=timedelta(
                seconds=int(os.environ.get("NETPULSE_AIRFLOW_STALE_AFTER_SECONDS", "900"))
            ),
            delay_after=timedelta(
                seconds=int(os.environ.get("NETPULSE_AIRFLOW_DELAY_AFTER_SECONDS", "600"))
            ),
        )
        run_id = str(get_current_context()["run_id"])
        repository.start_run(run_id, _selected(payload), assessment)
        if not assessment.may_refresh:
            raise RuntimeError(f"source quality status is {assessment.status.value}")
        return payload

    @task(
        task_id="run_analytics_refresh",
        retries=DAG_CONTRACT.retries_for("run_analytics_refresh"),
        retry_delay=timedelta(minutes=2),
        execution_timeout=DAG_CONTRACT.task_timeouts["run_analytics_refresh"],
    )
    def run_analytics(payload: dict[str, str]) -> dict[str, Any]:
        selected = _selected(payload)
        result = PostgresAnalyticsRepository(_database_url()).run(
            DateSelection(selected.from_date, selected.through_date, False)
        )
        return {**payload, "analytics_run_id": result.run_id}

    @task(
        task_id="reconcile_analytics",
        execution_timeout=DAG_CONTRACT.task_timeouts["reconcile_analytics"],
    )
    def reconcile_analytics(state: dict[str, Any]) -> dict[str, Any]:
        result = PostgresOrchestrationRepository(_database_url()).reconcile(_selected(state))
        result.require_valid()
        return {
            **state,
            "reconciliation": {
                "daily_source_rows": result.daily_source_rows,
                "daily_fact_rows": result.daily_fact_rows,
                "daily_mismatch_rows": result.daily_mismatch_rows,
                "source_incidents": result.source_incidents,
                "fact_incidents": result.fact_incidents,
                "incident_mismatch_rows": result.incident_mismatch_rows,
            },
        }

    @task(
        task_id="validate_reporting",
        execution_timeout=DAG_CONTRACT.task_timeouts["validate_reporting"],
    )
    def validate_reporting(state: dict[str, Any]) -> dict[str, Any]:
        result = PostgresOrchestrationRepository(_database_url()).validate_reporting(
            _selected(state), int(state["analytics_run_id"])
        )
        result.require_valid()
        return state

    @task(
        task_id="record_workflow_success",
        execution_timeout=DAG_CONTRACT.task_timeouts["record_workflow_success"],
    )
    def record_success(state: dict[str, Any]) -> None:
        PostgresOrchestrationRepository(_database_url()).record_success(
            str(get_current_context()["run_id"]),
            int(state["analytics_run_id"]),
            ReconciliationResult(**state["reconciliation"]),
        )

    selected_range = resolve_date_range()
    available_database = check_postgres(selected_range)
    accepted_source = assess_source(available_database)
    refreshed = run_analytics(accepted_source)
    reconciled = reconcile_analytics(refreshed)
    validated = validate_reporting(reconciled)
    record_success(validated)
