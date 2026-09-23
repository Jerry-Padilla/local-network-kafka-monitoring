"""Command-line interface for one-shot analytics refreshes."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date

import structlog

from netpulse_analytics.config import AnalyticsConfig


@dataclass(frozen=True, slots=True)
class DateSelection:
    from_date: date | None
    through_date: date | None
    is_all: bool


def parse_selection(argv: list[str] | None) -> DateSelection:
    parser = argparse.ArgumentParser(description="Refresh NetPulse analytics")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--all", action="store_true")
    choice.add_argument("--from-date", type=date.fromisoformat)
    parser.add_argument("--through-date", type=date.fromisoformat)
    args = parser.parse_args(argv)
    if args.all and args.through_date is not None:
        parser.error("--all cannot be combined with --through-date")
    if not args.all and (args.through_date is None or args.from_date > args.through_date):
        parser.error("provide an inclusive, ordered --from-date/--through-date pair")
    return DateSelection(args.from_date, args.through_date, args.all)


def _configure_logging() -> None:
    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


def main(argv: list[str] | None = None) -> int:
    selection = parse_selection(argv)
    config = AnalyticsConfig.from_env()
    _configure_logging()

    from netpulse_analytics.repository import PostgresAnalyticsRepository

    result = PostgresAnalyticsRepository(config.database_url).run(selection)
    structlog.get_logger().info(
        "analytics_refresh_completed",
        run_id=result.run_id,
        daily_rows=result.daily_rows,
        incident_rows=result.incident_rows,
    )
    return 0
