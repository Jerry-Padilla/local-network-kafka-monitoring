"""Command-line interface for headless and diagnostic agent operation."""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
from collections.abc import Sequence
from dataclasses import asdict

from netpulse_contracts.logging import configure_logging

from netpulse_agent.config import AgentConfigurationError, load_config
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_agent.runtime import AgentRuntime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netpulse-agent")
    parser.add_argument(
        "--config",
        default=os.getenv("NETPULSE_AGENT_CONFIG", "/etc/netpulse-agent/agent.yaml"),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="run collectors and delivery workers")
    commands.add_parser("validate-config", help="validate configuration without collecting")
    collect = commands.add_parser("collect-once", help="run each enabled collector once")
    collect.add_argument("--publish", action="store_true")
    commands.add_parser("outbox-status", help="print queue counters without payload data")
    commands.add_parser("publish-once", help="attempt one eligible outbox batch")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging("netpulse-network-agent")
    try:
        config = load_config(args.config)
    except AgentConfigurationError as error:
        print(f"configuration error: {error}")
        return 2

    if args.command == "validate-config":
        print(f"configuration valid for {config.agent.agent_id}")
        return 0

    if args.command == "outbox-status":
        stats = SQLiteOutbox(config.outbox).stats()
        print(json.dumps(asdict(stats), sort_keys=True))
        return 0

    runtime = AgentRuntime(config)
    if args.command == "collect-once":
        enqueued = runtime.collect_once()
        acknowledged, failed = runtime.publish_once() if args.publish else (0, 0)
        runtime.publisher.close()
        print(
            json.dumps(
                {
                    "enqueued": enqueued,
                    "acknowledged": acknowledged,
                    "failed": failed,
                    "outbox_depth": runtime.outbox.depth(),
                },
                sort_keys=True,
            )
        )
        return 1 if failed else 0
    if args.command == "publish-once":
        acknowledged, failed = runtime.publish_once()
        runtime.publisher.close()
        print(json.dumps({"acknowledged": acknowledged, "failed": failed}, sort_keys=True))
        return 1 if failed else 0

    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    runtime.run(stop_event)
    return 0
