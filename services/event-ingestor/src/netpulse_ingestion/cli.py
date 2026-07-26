"""Ingestion service entry point and health-check command."""

from __future__ import annotations

import argparse

from netpulse_contracts.logging import configure_logging

from netpulse_ingestion.config import IngestionConfig
from netpulse_ingestion.consumer import IngestionConsumer
from netpulse_ingestion.processor import EventProcessor
from netpulse_ingestion.publisher import SynchronousKafkaPublisher
from netpulse_ingestion.repository import PostgresEventRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NetPulse event ingestor")
    parser.add_argument(
        "command",
        choices=("run", "healthcheck"),
        nargs="?",
        default="run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging("netpulse-event-ingestor")
    args = _parser().parse_args(argv)
    config = IngestionConfig.from_env()
    repository = PostgresEventRepository(config.database_url)
    repository.open()
    try:
        if args.command == "healthcheck":
            return 0 if repository.healthcheck() else 1

        publisher = SynchronousKafkaPublisher(
            bootstrap_servers=config.bootstrap_servers,
            client_id=f"{config.client_id}-output",
            delivery_timeout_seconds=config.delivery_timeout_seconds,
        )
        try:
            processor = EventProcessor(repository, publisher)
            consumer = IngestionConsumer(config, processor)
            consumer.install_signal_handlers()
            consumer.run()
        finally:
            publisher.close()
    finally:
        repository.close()
    return 0
