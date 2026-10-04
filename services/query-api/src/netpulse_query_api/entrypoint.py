"""Build the API database URL from dedicated environment components."""

from __future__ import annotations

import os
from urllib.parse import quote


def main() -> None:
    """Set the encoded database URL and replace this process with Uvicorn."""
    user = quote(os.environ["QUERY_API_DATABASE_USER"], safe="")
    password = quote(os.environ["QUERY_API_DATABASE_PASSWORD"], safe="")
    host = os.environ["QUERY_API_DATABASE_HOST"]
    port = os.environ["QUERY_API_DATABASE_PORT"]
    database = quote(os.environ["QUERY_API_DATABASE_NAME"], safe="")
    os.environ["NETPULSE_DATABASE_URL"] = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "netpulse_query_api.main:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
    )
