from datetime import timedelta

from netpulse_analytics.orchestration.dag_contract import DAG_CONTRACT


def test_daily_reliability_dag_contract_is_bounded_and_non_overlapping() -> None:
    assert DAG_CONTRACT.dag_id == "netpulse_daily_reliability"
    assert DAG_CONTRACT.schedule == "0 2 * * *"
    assert DAG_CONTRACT.catchup is False
    assert DAG_CONTRACT.max_active_runs == 1
    assert DAG_CONTRACT.dag_timeout == timedelta(hours=1)
    assert DAG_CONTRACT.maximum_backfill_days == 31


def test_task_chain_and_retry_policies_distinguish_transient_from_quality_failures() -> None:
    assert DAG_CONTRACT.task_ids == (
        "resolve_date_range",
        "check_postgres",
        "assess_source_quality",
        "run_analytics_refresh",
        "reconcile_analytics",
        "validate_reporting",
        "record_workflow_success",
    )
    assert DAG_CONTRACT.retries_for("check_postgres") == 2
    assert DAG_CONTRACT.retries_for("run_analytics_refresh") == 2
    assert DAG_CONTRACT.retries_for("assess_source_quality") == 0
    assert DAG_CONTRACT.retries_for("reconcile_analytics") == 0
    assert all(timeout > timedelta(0) for timeout in DAG_CONTRACT.task_timeouts.values())
