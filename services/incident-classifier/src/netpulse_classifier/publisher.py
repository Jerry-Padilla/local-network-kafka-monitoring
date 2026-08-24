"""Acknowledged Kafka publication for the durable incident outbox."""

from __future__ import annotations

import time
from threading import Event

from confluent_kafka import KafkaError, Message, Producer


class IncidentPublicationError(RuntimeError):
    """Kafka did not acknowledge an incident state event."""


class IncidentPublisher:
    def __init__(
        self, bootstrap_servers: str, client_id: str, delivery_timeout_seconds: float
    ) -> None:
        self._delivery_timeout_seconds = delivery_timeout_seconds
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "client.id": client_id,
                "enable.idempotence": True,
                "acks": "all",
                "compression.type": "zstd",
                "retries": 5,
                "retry.backoff.ms": 250,
                "message.timeout.ms": int(delivery_timeout_seconds * 1_000),
                "max.in.flight.requests.per.connection": 5,
            }
        )

    def publish(self, topic: str, key: str, value: bytes) -> None:
        delivered = Event()
        errors: list[KafkaError] = []

        def callback(error: KafkaError | None, _message: Message) -> None:
            if error is not None:
                errors.append(error)
            delivered.set()

        deadline = time.monotonic() + self._delivery_timeout_seconds
        while True:
            try:
                self._producer.produce(topic, key=key, value=value, on_delivery=callback)
                break
            except BufferError as error:
                if time.monotonic() >= deadline:
                    raise IncidentPublicationError(
                        "incident producer queue remained full"
                    ) from error
                self._producer.poll(0.1)
        while not delivered.is_set() and time.monotonic() < deadline:
            self._producer.poll(0.1)
        if not delivered.is_set():
            raise IncidentPublicationError(f"delivery to {topic} timed out")
        if errors:
            raise IncidentPublicationError(f"delivery to {topic} failed: {errors[0]}")

    def close(self) -> None:
        remaining = self._producer.flush(self._delivery_timeout_seconds)
        if remaining:
            raise IncidentPublicationError(f"{remaining} incident records remained during shutdown")
