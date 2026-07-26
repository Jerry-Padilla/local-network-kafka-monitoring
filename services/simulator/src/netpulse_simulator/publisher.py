"""Reliable Kafka publication for simulated telemetry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import structlog
from confluent_kafka import KafkaError, Message, Producer

from netpulse_simulator.config import SimulatorConfig
from netpulse_simulator.scenarios import SimulatedRecord

LOGGER = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class PublishSummary:
    attempted: int
    acknowledged: int
    failed: int


class KafkaPublisher:
    """Thin producer wrapper with explicit delivery-result accounting."""

    def __init__(self, config: SimulatorConfig) -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": config.bootstrap_servers,
                "client.id": config.client_id,
                "enable.idempotence": True,
                "acks": "all",
                "compression.type": "zstd",
                "retries": 5,
                "retry.backoff.ms": 250,
                "message.timeout.ms": 10_000,
                "max.in.flight.requests.per.connection": 5,
            }
        )

    def publish_batch(
        self, records: Iterable[SimulatedRecord], timeout_seconds: float = 15
    ) -> PublishSummary:
        attempted = 0
        acknowledged = 0
        errors: list[KafkaError] = []

        def on_delivery(error: KafkaError | None, message: Message) -> None:
            nonlocal acknowledged
            if error is not None:
                errors.append(error)
                LOGGER.error(
                    "kafka_delivery_failed",
                    topic=message.topic(),
                    partition=message.partition(),
                    error=str(error),
                )
                return
            acknowledged += 1
            LOGGER.debug(
                "kafka_delivery_acknowledged",
                topic=message.topic(),
                partition=message.partition(),
                offset=message.offset(),
            )

        for record in records:
            attempted += 1
            while True:
                try:
                    self._producer.produce(
                        topic=record.topic,
                        key=record.key,
                        value=record.value,
                        on_delivery=on_delivery,
                    )
                    break
                except BufferError:
                    self._producer.poll(0.1)
            self._producer.poll(0)

        remaining = self._producer.flush(timeout_seconds)
        failed = len(errors) + remaining
        if failed:
            raise RuntimeError(
                f"Kafka failed to acknowledge {failed} of {attempted} simulated records"
            )
        return PublishSummary(attempted=attempted, acknowledged=acknowledged, failed=failed)

    def close(self) -> None:
        remaining = self._producer.flush(10)
        if remaining:
            raise RuntimeError(f"{remaining} Kafka messages remained during shutdown")
