"""Ingestion service entry point and health-check command."""

from __future__ import annotations

import argparse

from netpulse_contracts.logging import configure_logging
from netpulse_observability import MetricsServer
from prometheus_client import CollectorRegistry

from netpulse_ingestion.config import IngestionConfig
from netpulse_ingestion.consumer import IngestionConsumer
from netpulse_ingestion.metrics import IngestionMetrics
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

        known_agents, known_endpoints = repository.load_reference_ids()
        registry = CollectorRegistry()
        metrics = IngestionMetrics(registry)
        metrics_server = MetricsServer(config.metrics, registry)
        metrics_server.start()
        try:
            publisher = SynchronousKafkaPublisher(
                bootstrap_servers=config.bootstrap_servers,
                client_id=f"{config.client_id}-output",
                delivery_timeout_seconds=config.delivery_timeout_seconds,
                metrics=metrics,
            )
            try:
                processor = EventProcessor(
                    repository,
                    publisher,
                    known_agents=known_agents,
                    known_endpoints=known_endpoints,
                )
                consumer = IngestionConsumer(config, processor, metrics)
                consumer.install_signal_handlers()
                consumer.run()
            finally:
                publisher.close()
        finally:
            metrics_server.stop()
    finally:
        repository.close()
    return 0
