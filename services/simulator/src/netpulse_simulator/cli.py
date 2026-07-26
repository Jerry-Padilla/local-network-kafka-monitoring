"""Command-line interface for deterministic scenario publication."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import structlog
from netpulse_contracts.logging import configure_logging

from netpulse_simulator.config import SimulatorConfig
from netpulse_simulator.publisher import KafkaPublisher
from netpulse_simulator.scenarios import SCENARIOS, ScenarioGenerator, SimulatedRecord

LOGGER = structlog.get_logger()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NetPulse deterministic telemetry simulator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="publish a named scenario")
    run.add_argument("--scenario", choices=SCENARIOS, default="healthy")
    run.add_argument("--duration", type=int, default=60, help="duration in seconds")
    run.add_argument("--rate", type=float, default=1.0, help="rounds per second")
    run.add_argument("--seed", type=int)
    run.add_argument("--dry-run", action="store_true", help="print records without Kafka")

    load = subparsers.add_parser("load-test", help="publish at a target event rate")
    load.add_argument("--rate", type=int, required=True, help="target events per second")
    load.add_argument("--duration", type=int, required=True)
    load.add_argument("--seed", type=int)
    load.add_argument("--dry-run", action="store_true")
    return parser


def _emit_dry_run(records: Sequence[SimulatedRecord]) -> None:
    for record in records:
        value = record.value
        print(json.dumps(json.loads(value), sort_keys=True))


def _run_scenario(args: argparse.Namespace, config: SimulatorConfig) -> int:
    if args.duration <= 0 or args.rate <= 0:
        raise ValueError("duration and rate must be positive")
    generator = ScenarioGenerator(seed=args.seed if args.seed is not None else config.seed)
    publisher = None if args.dry_run else KafkaPublisher(config)
    started = datetime.now(UTC)
    deadline = time.monotonic() + args.duration
    interval = 1 / args.rate
    rounds = 0
    records_sent = 0
    try:
        while time.monotonic() < deadline:
            round_time = started + timedelta(seconds=rounds * interval)
            records = generator.generate_round(args.scenario, round_time)
            if publisher is None:
                _emit_dry_run(records)
            else:
                summary = publisher.publish_batch(records)
                records_sent += summary.acknowledged
            rounds += 1
            sleep_for = started.timestamp() + (rounds * interval) - datetime.now(UTC).timestamp()
            if sleep_for > 0:
                time.sleep(min(sleep_for, interval))
    finally:
        if publisher is not None:
            publisher.close()
    LOGGER.info(
        "scenario_complete",
        scenario=args.scenario,
        rounds=rounds,
        records_sent=records_sent,
        dry_run=args.dry_run,
    )
    return 0


def _run_load_test(args: argparse.Namespace, config: SimulatorConfig) -> int:
    if args.duration <= 0 or args.rate <= 0:
        raise ValueError("duration and rate must be positive")
    generator = ScenarioGenerator(seed=args.seed if args.seed is not None else config.seed)
    publisher = None if args.dry_run else KafkaPublisher(config)
    started = time.monotonic()
    deadline = started + args.duration
    records_sent = 0
    try:
        while time.monotonic() < deadline:
            batch: list[SimulatedRecord] = []
            while len(batch) < args.rate:
                batch.extend(generator.generate_round("burst-traffic"))
            batch = batch[: args.rate]
            if publisher is None:
                _emit_dry_run(batch)
            else:
                records_sent += publisher.publish_batch(batch).acknowledged
            next_second = started + (records_sent / args.rate if not args.dry_run else 1)
            sleep_for = next_second - time.monotonic()
            if sleep_for > 0:
                time.sleep(min(sleep_for, 1))
            if args.dry_run:
                break
    finally:
        if publisher is not None:
            publisher.close()
    LOGGER.info("load_test_complete", rate=args.rate, records_sent=records_sent)
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging("netpulse-simulator")
    args = _parser().parse_args(argv)
    config = SimulatorConfig.from_env()
    if args.command == "run":
        return _run_scenario(args, config)
    return _run_load_test(args, config)
