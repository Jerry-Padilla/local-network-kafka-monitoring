"""Version-independent contract consumed by the Airflow DAG and unit tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class DagContract:
    dag_id: str
    schedule: str
    catchup: bool
    max_active_runs: int
    dag_timeout: timedelta
    maximum_backfill_days: int
    task_ids: tuple[str, ...]
    transient_task_retries: Mapping[str, int]
    task_timeouts: Mapping[str, timedelta]

    def retries_for(self, task_id: str) -> int:
        return self.transient_task_retries.get(task_id, 0)


_TASK_IDS = (
    "resolve_date_range",
    "check_postgres",
    "assess_source_quality",
    "run_analytics_refresh",
    "reconcile_analytics",
    "validate_reporting",
    "record_workflow_success",
)

DAG_CONTRACT = DagContract(
    dag_id="netpulse_daily_reliability",
    schedule="0 2 * * *",
    catchup=False,
    max_active_runs=1,
    dag_timeout=timedelta(hours=1),
    maximum_backfill_days=31,
    task_ids=_TASK_IDS,
    transient_task_retries=MappingProxyType({"check_postgres": 2, "run_analytics_refresh": 2}),
    task_timeouts=MappingProxyType(
        {
            "resolve_date_range": timedelta(seconds=30),
            "check_postgres": timedelta(seconds=30),
            "assess_source_quality": timedelta(minutes=2),
            "run_analytics_refresh": timedelta(minutes=20),
            "reconcile_analytics": timedelta(minutes=10),
            "validate_reporting": timedelta(minutes=5),
            "record_workflow_success": timedelta(minutes=1),
        }
    ),
)
