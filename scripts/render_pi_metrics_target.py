#!/usr/bin/env python3
"""Render the single mandatory Pi Prometheus target without accepting URLs."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
from pathlib import Path

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "deployment/observability/prometheus/pi-targets.json"
)
HOSTNAME = re.compile(
    r"(?=^.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)


def _validated_host(value: str) -> str:
    if value != value.strip() or ":" in value or "/" in value or "*" in value:
        raise ValueError("provide one IPv4 address or hostname without a scheme or port")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if not HOSTNAME.fullmatch(value) or "." not in value:
            raise ValueError(
                "target must be a valid private IPv4 address or qualified hostname"
            ) from None
        return value.lower()
    if address.version != 4 or not address.is_private or address.is_unspecified:
        raise ValueError("IPv4 target must be a specific private address")
    return str(address)


def render(target: str, output: Path = DEFAULT_OUTPUT) -> None:
    host = _validated_host(target)
    document = [
        {"targets": [f"{host}:9102"], "labels": {"agent": "raspberry-pi", "required": "true"}}
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        render(args.target, args.output)
    except ValueError as error:
        parser.error(str(error))
    print(f"Rendered mandatory Pi metrics target to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
