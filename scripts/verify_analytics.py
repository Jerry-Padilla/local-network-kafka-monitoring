"""Reconcile current analytics facts with deduplicated operational tables."""

from __future__ import annotations

import os

from netpulse_analytics.orchestration.repository import PostgresOrchestrationRepository


def main() -> int:
    result = PostgresOrchestrationRepository(os.environ["NETPULSE_DATABASE_URL"]).reconcile_all()
    if not result.valid:
        print(
            "FAILED: analytics reconciliation mismatch: "
            f"daily={result.daily_mismatch_rows}, incidents={result.incident_mismatch_rows}"
        )
        return 1
    print(
        "Phase 5A analytics invariants passed: "
        f"{result.daily_fact_rows} daily grains, {result.fact_incidents} incidents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
