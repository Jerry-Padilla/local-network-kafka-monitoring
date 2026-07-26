from __future__ import annotations

from netpulse_agent.collector_types import CollectedEvent
from netpulse_agent.events import EventFactory
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_agent.scheduler import CollectionErrorTracker, CollectorWorker


class FailingCollector:
    name = "failing"
    interval_seconds = 1.0

    def collect(self) -> list[CollectedEvent]:
        raise RuntimeError("sensitive details are not copied")


def test_collector_failure_is_sanitized_and_does_not_escape(
    event_factory: EventFactory,
    outbox: SQLiteOutbox,
) -> None:
    errors = CollectionErrorTracker()
    worker = CollectorWorker(FailingCollector(), event_factory, outbox, errors)

    assert worker.collect_once() == 0
    assert len(errors.snapshot()) == 1
    assert errors.snapshot()[0].endswith("failing: RuntimeError")
    assert outbox.depth() == 0
