"""Construct the tests-only query API login URL before starting pytest."""

from __future__ import annotations

import os
import sys
from urllib.parse import quote


def build_query_api_url(user: str, password: str, host: str, port: str, database: str) -> str:
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
    )


def main() -> None:
    os.environ["NETPULSE_QUERY_API_DATABASE_URL"] = build_query_api_url(
        os.environ["QUERY_API_DATABASE_USER"],
        os.environ["QUERY_API_DATABASE_PASSWORD"],
        os.environ["QUERY_API_DATABASE_HOST"],
        os.environ["QUERY_API_DATABASE_PORT"],
        os.environ["QUERY_API_DATABASE_NAME"],
    )
    os.execvp("python", ["python", "-m", "pytest", *sys.argv[1:]])


if __name__ == "__main__":
    main()
