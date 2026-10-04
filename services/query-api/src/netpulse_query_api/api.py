"""Read-only HTTP routes and safe request handling for daily reliability."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from pydantic import ValidationError

from netpulse_query_api.cursor import CursorError, decode_cursor, encode_cursor
from netpulse_query_api.models import (
    CursorKey,
    DailyReliabilityFilters,
    DailyReliabilityPage,
)
from netpulse_query_api.repository import ReliabilityRepository

_LOGGER = logging.getLogger("netpulse_query_api")
_QUERY_KEYS = frozenset(
    {
        "from_date",
        "through_date",
        "agent_id",
        "endpoint_id",
        "source_kind",
        "probe_type",
        "cursor",
        "limit",
    }
)
_LIMIT_PATTERN = re.compile(r"[0-9]+\Z")
_CURSOR_KEY_FIELDS = {"date_utc", "agent_id", "endpoint_id", "source_kind", "probe_type"}
_QUERY_PARAMETERS = (
    [
        {
            "name": name,
            "in": "query",
            "required": False,
            "description": "Inclusive UTC date; supply both dates, in order, within 366 days.",
            "schema": {"type": "string", "format": "date"},
        }
        for name in ("from_date", "through_date")
    ]
    + [
        {
            "name": name,
            "in": "query",
            "required": False,
            "description": "Exact, case-sensitive match.",
            "schema": {"type": "string", "minLength": 1, "maxLength": 128},
        }
        for name in ("agent_id", "endpoint_id", "probe_type")
    ]
    + [
        {
            "name": "source_kind",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "enum": ["network_measurement", "service_check"]},
        },
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
        },
        {
            "name": "cursor",
            "in": "query",
            "required": False,
            "description": (
                "Opaque continuation token from the previous page; keep filters unchanged."
            ),
            "schema": {"type": "string", "maxLength": 2048},
        },
    ]
)


def _request_id(value: str | None) -> str:
    if value and len(value) <= 128 and all(32 <= ord(char) <= 126 for char in value):
        return value
    return str(uuid.uuid4())


def _parse_query(request: Request) -> tuple[DailyReliabilityFilters, CursorKey | None, int]:
    pairs = request.query_params.multi_items()
    names = [name for name, _ in pairs]
    if len(names) != len(set(names)) or not set(names) <= _QUERY_KEYS:
        raise HTTPException(status_code=422, detail="invalid query parameters")
    values = dict(pairs)
    limit_text = values.pop("limit", "50")
    if len(limit_text) > 3 or _LIMIT_PATTERN.fullmatch(limit_text) is None:
        raise HTTPException(status_code=422, detail="invalid query parameters")
    limit = int(limit_text)
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="invalid query parameters")
    token = values.pop("cursor", None)
    try:
        filters = DailyReliabilityFilters.model_validate(values)
    except ValidationError:
        raise HTTPException(status_code=422, detail="invalid query parameters") from None
    try:
        cursor = decode_cursor(token, filters) if token is not None else None
    except CursorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return filters, cursor, limit


def build_app(
    repository: ReliabilityRepository,
    *,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """Build the same routes for isolated tests and production startup."""
    app = FastAPI(
        title="NetPulse Query API",
        version="1.0.0",
        lifespan=lifespan,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request_id = _request_id(request.headers.get("X-Request-ID"))
        request.state.row_count = 0
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except (PoolTimeout, OperationalError):
            response = JSONResponse(status_code=503, content={"detail": "database unavailable"})
        except Exception:
            response = JSONResponse(status_code=500, content={"detail": "internal server error"})
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        _LOGGER.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "route_template": route_template,
                    "status": response.status_code,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "row_count": request.state.row_count,
                }
            ),
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "invalid query parameters"})

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        if not await repository.health():
            raise HTTPException(status_code=503, detail="database unavailable")
        return {"status": "ok"}

    @app.get(
        "/v1/reliability/daily",
        response_model=DailyReliabilityPage,
        responses={422: {"description": "Invalid query parameters or cursor."}},
        openapi_extra={"parameters": _QUERY_PARAMETERS},
    )
    async def daily(request: Request) -> DailyReliabilityPage:
        filters, cursor, limit = _parse_query(request)
        page = await repository.list_daily(filters, cursor, limit)
        items = list(page.rows)
        request.state.row_count = len(items)
        next_cursor = None
        if page.has_more and items:
            key = CursorKey.model_validate(items[-1].model_dump(include=_CURSOR_KEY_FIELDS))
            next_cursor = encode_cursor(key, filters)
        return DailyReliabilityPage(items=items, next_cursor=next_cursor, limit=limit)

    return app
