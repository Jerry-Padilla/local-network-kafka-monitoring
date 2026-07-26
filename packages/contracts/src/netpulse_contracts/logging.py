"""Structured logging configuration shared by services."""

from __future__ import annotations

import logging
import os
import sys

import structlog


def configure_logging(service_name: str, level: str | None = None) -> None:
    """Configure newline-delimited JSON logs for a service."""
    configured_level = level if level is not None else os.getenv("NETPULSE_LOG_LEVEL")
    resolved_level = (configured_level or "INFO").upper()
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, resolved_level, logging.INFO),
        stream=sys.stdout,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, resolved_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)
