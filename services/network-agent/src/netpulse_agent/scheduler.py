"""Independent collector workers and bounded error tracking."""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import UTC, datetime

import structlog

from netpulse_agent.collector_types import Collector
from netpulse_agent.events import EventFactory
from netpulse_agent.metrics import AgentMetrics
from netpulse_agent.outbox import SQLiteOutbox

LOGGER = structlog.get_logger()


class CollectionErrorTracker:
    """Keep recent sanitized collector failures for heartbeat reporting."""

    def __init__(self, maximum: int = 20) -> None:
        self._errors: deque[str] = deque(maxlen=maximum)
        self._lock = threading.Lock()

    def add(self, collector_name: str, error: Exception) -> None:
        timestamp = datetime.now(UTC).isoformat()
        message = f"{timestamp} {collector_name}: {type(error).__name__}"
        with self._lock:
            self._errors.append(message)

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self._errors)


class CollectorWorker:
    """Run one collector on its own schedule and enqueue validated events."""

    def __init__(
        self,
        collector: Collector,
        event_factory: EventFactory,
        outbox: SQLiteOutbox,
        errors: CollectionErrorTracker,
        metrics: AgentMetrics,
    ) -> None:
        self._collector = collector
        self._event_factory = event_factory
        self._outbox = outbox
        self._errors = errors
        self._metrics = metrics

    def collect_once(self) -> int:
        """Collect and durably enqueue one invocation."""
        enqueued = 0
        try:
            for collected in self._collector.collect():
                event = self._event_factory.build(collected)
                if self._outbox.enqueue(event):
                    enqueued += 1
            self._metrics.record_collection(
                self._collector.name,
                "succeeded",
                timestamp_seconds=time.time(),
            )
        except Exception as error:
            self._errors.add(self._collector.name, error)
            self._metrics.record_collection(self._collector.name, "failed")
            LOGGER.exception("collector_failed", collector=self._collector.name)
        self._metrics.set_outbox(
            self._outbox.depth(),
            self._outbox.oldest_pending_age_seconds(),
        )
        return enqueued

    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self.collect_once()
            stop_event.wait(self._collector.interval_seconds)
