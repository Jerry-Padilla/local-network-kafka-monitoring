"""Composition root for the headless network agent."""

from __future__ import annotations

import threading

import structlog

from netpulse_agent.collector_types import Collector
from netpulse_agent.collectors import (
    DnsCollector,
    HeartbeatCollector,
    HttpCollector,
    PingCollector,
    SpeedTestCollector,
    WifiCollector,
)
from netpulse_agent.config import AgentConfig
from netpulse_agent.events import EventFactory
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_agent.publisher import OutboxDeliveryWorker, OutboxPublisher
from netpulse_agent.scheduler import CollectionErrorTracker, CollectorWorker

LOGGER = structlog.get_logger()


def build_collectors(
    config: AgentConfig,
    outbox: SQLiteOutbox,
    errors: CollectionErrorTracker,
) -> list[Collector]:
    """Construct only enabled collectors from validated configuration."""
    collectors: list[Collector] = []
    configured = config.collectors
    if configured.router_ping.enabled:
        collectors.append(
            PingCollector(
                "router_ping",
                "router_ping",
                configured.router_ping,
                config.privacy,
            )
        )
    if configured.external_ping.enabled:
        collectors.append(
            PingCollector(
                "external_ping",
                "external_ping",
                configured.external_ping,
                config.privacy,
            )
        )
    if configured.dns.enabled:
        collectors.append(DnsCollector(configured.dns, config.privacy))
    if configured.http.enabled:
        collectors.append(HttpCollector(configured.http, config.privacy))
    if configured.wifi.enabled:
        collectors.append(WifiCollector(configured.wifi, config.privacy))
    if configured.heartbeat.enabled:
        collectors.append(
            HeartbeatCollector(
                configured.heartbeat.interval_seconds,
                config.agent.source_version,
                outbox.depth,
                errors.snapshot,
            )
        )
    if configured.speed_test.enabled:
        collectors.append(SpeedTestCollector(configured.speed_test))
    return collectors


class AgentRuntime:
    """Own worker threads while preserving collection/delivery independence."""

    def __init__(
        self,
        config: AgentConfig,
        outbox: SQLiteOutbox | None = None,
        publisher: OutboxPublisher | None = None,
        collectors: list[Collector] | None = None,
    ) -> None:
        self.config = config
        self.outbox = outbox or SQLiteOutbox(config.outbox)
        self.errors = CollectionErrorTracker()
        self.event_factory = EventFactory(config.agent, self.outbox.next_sequence)
        active_collectors = collectors or build_collectors(config, self.outbox, self.errors)
        self.workers = [
            CollectorWorker(item, self.event_factory, self.outbox, self.errors)
            for item in active_collectors
        ]
        self.publisher = publisher or OutboxPublisher(config.kafka, self.outbox)
        self.delivery_worker = OutboxDeliveryWorker(
            self.publisher,
            config.kafka.poll_interval_seconds,
        )

    def collect_once(self) -> int:
        return sum(worker.collect_once() for worker in self.workers)

    def publish_once(self) -> tuple[int, int]:
        return self.publisher.publish_ready()

    def run(self, stop_event: threading.Event) -> None:
        """Run one thread per collector plus one delivery thread."""
        threads = [
            threading.Thread(
                target=worker.run,
                args=(stop_event,),
                name=f"netpulse-{index}",
                daemon=True,
            )
            for index, worker in enumerate(self.workers)
        ]
        threads.append(
            threading.Thread(
                target=self.delivery_worker.run,
                args=(stop_event,),
                name="netpulse-publisher",
                daemon=True,
            )
        )
        for thread in threads:
            thread.start()
        LOGGER.info("agent_started", collectors=len(self.workers))
        try:
            while not stop_event.wait(1):
                pass
        finally:
            for thread in threads:
                thread.join(timeout=5)
            self.publisher.close()
            LOGGER.info("agent_stopped", outbox_depth=self.outbox.depth())
