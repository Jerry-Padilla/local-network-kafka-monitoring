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


def create_app() -> FastAPI:
    """Construct the service without opening its pool until startup."""
    config = QueryApiConfig.from_env()
    logging.basicConfig(format="%(message)s", level=config.log_level.upper())
    logging.getLogger("netpulse_query_api").setLevel(config.log_level.upper())
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
