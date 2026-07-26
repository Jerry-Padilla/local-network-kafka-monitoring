"""Shared collector interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CollectedEvent:
    """Event-specific fields produced by one collector invocation."""

    event_type: str
    fields: dict[str, object]


class Collector(Protocol):
    """A collector that never performs Kafka or database work."""

    name: str
    interval_seconds: float

    def collect(self) -> list[CollectedEvent]:
        """Collect zero or more event payloads."""
        ...
