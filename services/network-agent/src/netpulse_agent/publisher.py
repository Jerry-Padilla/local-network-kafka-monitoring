"""Kafka delivery worker for durable outbox records."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol

import structlog
from confluent_kafka import KafkaError, KafkaException, Message, Producer

from netpulse_agent.config import KafkaConfig
from netpulse_agent.outbox import OutboxRecord, SQLiteOutbox

LOGGER = structlog.get_logger()
DeliveryCallback = Callable[[KafkaError | None, Message], None]


class ProducerLike(Protocol):
    def produce(
        self,
        topic: str,
        value: bytes,
        key: str,
        on_delivery: DeliveryCallback,
    ) -> None: ...

    def poll(self, timeout: float) -> int: ...

    def flush(self, timeout: float) -> int: ...


class OutboxPublisher:
    """Publish eligible records and mutate SQLite only from delivery outcomes."""

    def __init__(
        self,
        config: KafkaConfig,
        outbox: SQLiteOutbox,
        producer: ProducerLike | None = None,
    ) -> None:
        self._config = config
        self._outbox = outbox
        self._producer = producer or Producer(
            {
                "bootstrap.servers": config.bootstrap_servers,
                "client.id": config.client_id,
                "enable.idempotence": True,
                "acks": "all",
                "compression.type": config.compression,
                "retries": 5,
                "retry.backoff.ms": 250,
                "message.timeout.ms": int(config.delivery_timeout_seconds * 1_000),
                "max.in.flight.requests.per.connection": 5,
            }
        )

    def publish_ready(self) -> tuple[int, int]:
        """Attempt one ready batch and return acknowledged/failed counts."""
        acknowledged = 0
        failed = 0
        for record in self._outbox.ready():
            if self._publish_one(record):
                acknowledged += 1
            else:
                failed += 1
        self._outbox.prune_acknowledged()
        return acknowledged, failed

    def _publish_one(self, record: OutboxRecord) -> bool:
        completed = threading.Event()
        delivery_error: list[str] = []

        def on_delivery(error: KafkaError | None, _message: Message) -> None:
            if error is not None:
                delivery_error.append(str(error))
            completed.set()

        try:
            self._producer.produce(
                topic=record.topic,
                key=record.message_key,
                value=record.payload,
                on_delivery=on_delivery,
            )
        except (BufferError, KafkaException) as error:
            self._outbox.mark_failed(record, str(error))
            return False

        deadline = time.monotonic() + self._config.delivery_timeout_seconds
        while not completed.is_set() and time.monotonic() < deadline:
            self._producer.poll(min(0.1, max(0.0, deadline - time.monotonic())))
        if not completed.is_set():
            self._outbox.mark_failed(record, "Kafka delivery callback timed out")
            return False
        if delivery_error:
            self._outbox.mark_failed(record, delivery_error[0])
            return False
        self._outbox.mark_delivered(record.event_id)
        return True

    def close(self) -> None:
        """Flush callbacks without altering records lacking acknowledgements."""
        remaining = self._producer.flush(self._config.delivery_timeout_seconds)
        if remaining:
            LOGGER.warning("publisher_closed_with_pending_callbacks", remaining=remaining)


class OutboxDeliveryWorker:
    """Continuously drain eligible records without controlling collection."""

    def __init__(self, publisher: OutboxPublisher, poll_interval_seconds: float) -> None:
        self._publisher = publisher
        self._poll_interval_seconds = poll_interval_seconds

    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            acknowledged, failed = self._publisher.publish_ready()
            if acknowledged or failed:
                LOGGER.info(
                    "outbox_delivery_batch",
                    acknowledged=acknowledged,
                    failed=failed,
                )
            stop_event.wait(self._poll_interval_seconds)
