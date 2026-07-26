from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import psycopg
import pytest
from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.config import (
    AgentIdentityConfig,
    KafkaConfig,
    OutboxConfig,
)
from netpulse_agent.events import EventFactory
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_agent.publisher import OutboxPublisher
from netpulse_contracts.models import AgentRole

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.getenv("NETPULSE_INTEGRATION") == "1"


@pytest.mark.skipif(not _integration_enabled(), reason="set NETPULSE_INTEGRATION=1")
def test_agent_retains_event_offline_then_delivers_original_event(tmp_path) -> None:
    outbox = SQLiteOutbox(
        OutboxConfig(
            path=tmp_path / "agent-outbox.db",
            maximum_bytes=4_194_304,
            retry_base_seconds=0.25,
            retry_max_seconds=1,
            acknowledged_retention_seconds=60,
        )
    )
    observed_at = datetime.now(UTC)
    event = EventFactory(
        AgentIdentityConfig(
            agent_id="network-agent-wifi-01",
            role=AgentRole.WIFI_OBSERVER,
            source_version="0.2.0",
        ),
        outbox.next_sequence,
        now=lambda: observed_at,
    ).build(
        CollectedEvent(
            "network.measurement",
            {
                "measurement_type": "external_ping",
                "target_id": "public-dns-a",
                "success": True,
                "latency_ms": 7.5,
                "packet_loss_pct": 0,
            },
        )
    )
    assert outbox.enqueue(event)

    offline = OutboxPublisher(
        KafkaConfig(
            bootstrap_servers="127.0.0.1:1",
            delivery_timeout_seconds=0.5,
        ),
        outbox,
    )
    assert offline.publish_ready() == (0, 1)
    offline.close()
    assert outbox.depth() == 1
    assert outbox.stats().delivered_retained == 0

    time.sleep(0.4)
    online = OutboxPublisher(
        KafkaConfig(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            delivery_timeout_seconds=5,
        ),
        outbox,
    )
    assert online.publish_ready() == (1, 0)
    online.close()
    assert outbox.depth() == 0

    database_url = os.environ["NETPULSE_DATABASE_URL"]
    deadline = time.monotonic() + 20
    stored_time = None
    while time.monotonic() < deadline:
        with psycopg.connect(database_url) as connection:
            row = connection.execute(
                "SELECT event_time FROM raw_events WHERE event_id = %s",
                (event.event_id,),
            ).fetchone()
        if row is not None:
            stored_time = row[0]
            break
        time.sleep(0.5)

    assert stored_time == observed_at
