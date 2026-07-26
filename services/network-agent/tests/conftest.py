from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.config import AgentIdentityConfig, OutboxConfig
from netpulse_agent.events import EventFactory
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_contracts.models import AgentRole, Event


@pytest.fixture
def outbox(tmp_path: Path) -> SQLiteOutbox:
    return SQLiteOutbox(
        OutboxConfig(
            path=tmp_path / "outbox.db",
            maximum_bytes=4_194_304,
            batch_size=10,
            retry_base_seconds=2,
            retry_max_seconds=10,
            acknowledged_retention_seconds=5,
        )
    )


@pytest.fixture
def event_factory(outbox: SQLiteOutbox) -> EventFactory:
    return EventFactory(
        AgentIdentityConfig(
            agent_id="network-agent-wifi-01",
            role=AgentRole.WIFI_OBSERVER,
            source_version="0.2.0",
        ),
        outbox.next_sequence,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def measurement_event(event_factory: EventFactory) -> Event:
    return event_factory.build(
        CollectedEvent(
            "network.measurement",
            {
                "measurement_type": "external_ping",
                "target_id": "probe-a",
                "success": True,
                "latency_ms": 12.5,
                "packet_loss_pct": 0.0,
                "jitter_ms": 1.0,
            },
        )
    )
