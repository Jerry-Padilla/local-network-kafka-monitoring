"""Bounded operator check for the live daily reliability API."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

ORDER_FIELDS = ("date_utc", "agent_id", "endpoint_id", "source_kind", "probe_type")


def _read_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise ValueError("query API returned a non-success status")
        payload: object = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("query API returned a non-object response")
    return payload


def _page(base_url: str, cursor: str | None = None) -> dict[str, Any]:
    params = {"limit": "1"}
    if cursor is not None:
        params["cursor"] = cursor
    return _read_json(f"{base_url}/v1/reliability/daily?{urlencode(params)}")


def _keys(page: Mapping[str, Any]) -> set[tuple[object, ...]]:
    items = page.get("items")
    if not isinstance(items, list) or len(items) > 1:
        raise ValueError("query API returned an invalid page size")
    return {tuple(item[field] for field in ORDER_FIELDS) for item in items}


def verify(base_url: str) -> tuple[int, int]:
    health = _read_json(f"{base_url}/healthz")
    if health != {"status": "ok"}:
        raise ValueError("query API health response was invalid")
    first = _page(base_url)
    first_keys = _keys(first)
    second_count = 0
    next_cursor = first.get("next_cursor")
    if next_cursor is not None:
        if not isinstance(next_cursor, str) or not next_cursor or not first_keys:
            raise ValueError("query API cursor response was invalid")
        second = _page(base_url, next_cursor)
        second_keys = _keys(second)
        if first_keys & second_keys:
            raise ValueError("query API repeated an ordering key across pages")
        second_count = len(second_keys)
    return len(first_keys), second_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        first_count, second_count = verify(args.base_url.rstrip("/"))
    except Exception as exc:
        print(f"Query API verification failed: {type(exc).__name__}")
        return 1
    print("Query API health: OK")
    print(f"Daily reliability first page: {first_count} row(s)")
    print(f"Daily reliability second page: {second_count} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
