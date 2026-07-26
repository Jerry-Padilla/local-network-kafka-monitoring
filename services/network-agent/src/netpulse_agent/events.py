"""Versioned event-envelope construction."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from netpulse_contracts.models import Event
from netpulse_contracts.validation import validate_event

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.config import AgentIdentityConfig


class EventFactory:
    """Build validated v1 events with stable agent identity and sequence numbers."""

    def __init__(
        self,
        identity: AgentIdentityConfig,
        next_sequence: Callable[[], int],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._identity = identity
        self._next_sequence = next_sequence
        self._now = now or (lambda: datetime.now(UTC))

    def build(self, collected: CollectedEvent) -> Event:
        """Add the envelope and validate the resulting event contract."""
        current_time = self._now()
        payload: dict[str, object] = {
            "event_id": str(uuid4()),
            "event_type": collected.event_type,
            "schema_version": 1,
            "agent_id": self._identity.agent_id,
            "agent_role": self._identity.role,
            "event_time": current_time,
            "published_time": current_time,
            "sequence_number": self._next_sequence(),
            "correlation_id": None,
            "source_version": self._identity.source_version,
            **collected.fields,
        }
        return validate_event(payload)
