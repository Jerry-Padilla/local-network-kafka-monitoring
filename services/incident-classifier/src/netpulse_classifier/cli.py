"""Command-line entry point for periodic or one-shot classification."""

from __future__ import annotations

import argparse
import signal
from threading import Event

from netpulse_contracts.logging import configure_logging

from netpulse_classifier.config import ClassifierConfig
from netpulse_classifier.engine import ClassificationEngine
from netpulse_classifier.publisher import IncidentPublisher
from netpulse_classifier.repository import PostgresIncidentRepository
from netpulse_classifier.service import IncidentClassifierService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NetPulse deterministic incident classifier")
    parser.add_argument("command", choices=("run", "once", "healthcheck"), nargs="?", default="run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging("netpulse-incident-classifier")
    config = ClassifierConfig.from_env()
    repository = PostgresIncidentRepository(config.database_url)
    repository.open()
    try:
        if args.command == "healthcheck":
            return 0 if repository.healthcheck() else 1
        publisher = IncidentPublisher(
            config.bootstrap_servers,
            config.client_id,
            config.delivery_timeout_seconds,
        )
        try:
            service = IncidentClassifierService(
                config, repository, publisher, ClassificationEngine(config)
            )
            if args.command == "once":
                service.evaluate_once()
                return 0
            stopped = Event()

            def stop(_signum: int, _frame: object) -> None:
                stopped.set()

            signal.signal(signal.SIGINT, stop)
            signal.signal(signal.SIGTERM, stop)
            while not stopped.is_set():
                service.evaluate_once()
                stopped.wait(config.interval_seconds)
        finally:
            publisher.close()
    finally:
        repository.close()
    return 0
