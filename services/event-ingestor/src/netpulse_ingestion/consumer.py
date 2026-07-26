"""Manual-offset Kafka consumer with bounded replay retries."""

from __future__ import annotations

import random
import signal
import time

import structlog
from confluent_kafka import Consumer, KafkaError, KafkaException, Message, TopicPartition
from netpulse_contracts.topics import RAW_INPUT_TOPICS

from netpulse_ingestion.config import IngestionConfig
from netpulse_ingestion.processor import EventProcessor
from netpulse_ingestion.processor_types import SourceRecord

LOGGER = structlog.get_logger()


class IngestionConsumer:
    """Poll raw topics and commit each record only after complete processing."""

    def __init__(self, config: IngestionConfig, processor: EventProcessor) -> None:
        self._config = config
        self._processor = processor
        self._running = True
        self._consumer = Consumer(
            {
                "bootstrap.servers": config.bootstrap_servers,
                "group.id": config.consumer_group,
                "client.id": config.client_id,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
                "allow.auto.create.topics": False,
                "session.timeout.ms": 10_000,
                "max.poll.interval.ms": 60_000,
            }
        )

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._request_shutdown)
        signal.signal(signal.SIGTERM, self._request_shutdown)

    def _request_shutdown(self, _signum: int, _frame: object) -> None:
        LOGGER.info("shutdown_requested")
        self._running = False

    def run(self) -> None:
        self._consumer.subscribe(
            list(RAW_INPUT_TOPICS),
            on_assign=self._on_assign,
            on_revoke=self._on_revoke,
        )
        attempts: dict[tuple[str, int, int], int] = {}
        try:
            while self._running:
                message = self._consumer.poll(1)
                if message is None:
                    continue
                if message.error():
                    if message.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(message.error())

                coordinate = (message.topic(), message.partition(), message.offset())
                try:
                    source = self._to_source(message)
                    result = self._processor.process(source)
                    self._consumer.store_offsets(message=message)
                    self._consumer.commit(message=message, asynchronous=False)
                    attempts.pop(coordinate, None)
                    LOGGER.info(
                        "record_processed",
                        topic=message.topic(),
                        partition=message.partition(),
                        offset=message.offset(),
                        outcome=result.outcome.value,
                        event_id=result.event_id,
                    )
                except Exception as error:
                    attempt = attempts.get(coordinate, 0) + 1
                    attempts[coordinate] = attempt
                    LOGGER.exception(
                        "record_processing_failed",
                        topic=message.topic(),
                        partition=message.partition(),
                        offset=message.offset(),
                        attempt=attempt,
                    )
                    if attempt >= self._config.max_processing_attempts:
                        raise RuntimeError(
                            f"processing failed {attempt} times at {coordinate}; "
                            "stopping without committing the offset"
                        ) from error
                    self._consumer.seek(
                        TopicPartition(message.topic(), message.partition(), message.offset())
                    )
                    backoff = self._config.retry_base_seconds * (2 ** (attempt - 1))
                    time.sleep(backoff + random.uniform(0, backoff * 0.25))
        finally:
            self._consumer.close()
            LOGGER.info("consumer_closed")

    @staticmethod
    def _to_source(message: Message) -> SourceRecord:
        raw_key = message.key()
        if isinstance(raw_key, bytes):
            key = raw_key.decode("utf-8", errors="replace")
        elif raw_key is None:
            key = None
        else:
            key = str(raw_key)
        raw_value = message.value()
        value = raw_value if isinstance(raw_value, bytes) else str(raw_value).encode()
        return SourceRecord(
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            key=key,
            value=value,
        )

    def _on_assign(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        LOGGER.info("partitions_assigned", partitions=[str(item) for item in partitions])
        consumer.assign(partitions)

    def _on_revoke(self, _consumer: Consumer, partitions: list[TopicPartition]) -> None:
        LOGGER.info("partitions_revoked", partitions=[str(item) for item in partitions])
