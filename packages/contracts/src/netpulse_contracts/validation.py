"""Parse and validate untrusted event payloads."""

from __future__ import annotations

import json
from typing import Any

from pydantic import TypeAdapter, ValidationError

from netpulse_contracts.models import Event

_EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


class EventValidationError(ValueError):
    """An event cannot be decoded or does not satisfy its versioned contract."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def validate_event(payload: bytes | str | dict[str, object]) -> Event:
    """Decode and validate one event, preserving additive fields."""
    candidate: object
    if isinstance(payload, bytes):
        try:
            candidate = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EventValidationError(f"invalid UTF-8 JSON: {error}") from error
    elif isinstance(payload, str):
        try:
            candidate = json.loads(payload)
        except json.JSONDecodeError as error:
            raise EventValidationError(f"invalid JSON: {error}") from error
    else:
        candidate = payload

    if not isinstance(candidate, dict):
        raise EventValidationError("event must be a JSON object")

    try:
        return _EVENT_ADAPTER.validate_python(candidate)
    except ValidationError as error:
        errors = [dict(item) for item in error.errors()]
        raise EventValidationError("event contract validation failed", errors) from error
