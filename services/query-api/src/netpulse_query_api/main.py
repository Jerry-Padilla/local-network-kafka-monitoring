"""Uvicorn factory and PostgreSQL pool lifespan for the query API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from netpulse_query_api.api import build_app
from netpulse_query_api.config import QueryApiConfig
from netpulse_query_api.repository import PostgresReliabilityRepository


def _configure_logging(level: str) -> None:
    # Uvicorn initializes its loggers before loading an app factory. Its access
    # message contains the raw query string; psycopg can log connection errors.
    sensitive_names = [
        name
        for name in logging.Logger.manager.loggerDict
        if name == "psycopg" or name.startswith("psycopg.")
    ]
    for name in (*sensitive_names, "psycopg", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL + 1)
        logger.disabled = True

    logger = logging.getLogger("netpulse_query_api")
    logger.setLevel(level.upper())
    logger.propagate = False
    if not any(handler.get_name() == "netpulse-query-api" for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.set_name("netpulse-query-api")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


def create_app() -> FastAPI:
    """Construct the service without opening its pool until startup."""
    config = QueryApiConfig.from_env()
    _configure_logging(config.log_level)
    pool = AsyncConnectionPool(
        config.database_url,
        min_size=config.pool_min_size,
        max_size=config.pool_max_size,
        timeout=config.pool_acquire_timeout_seconds,
        kwargs={"options": "-c default_transaction_read_only=on"},
        open=False,
    )
    repository = PostgresReliabilityRepository(
        pool, statement_timeout_ms=config.statement_timeout_ms
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await pool.open()
        try:
            yield
        finally:
            await pool.close()

    return build_app(repository, lifespan=lifespan)
