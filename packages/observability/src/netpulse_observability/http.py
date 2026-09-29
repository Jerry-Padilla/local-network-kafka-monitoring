"""Validated Prometheus HTTP server configuration and lifecycle."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from threading import Thread
from wsgiref.simple_server import WSGIServer

from prometheus_client import CollectorRegistry, start_http_server


@dataclass(frozen=True, slots=True)
class MetricsHttpConfig:
    """Configuration shared by each service's internal metrics endpoint."""

    enabled: bool
    host: str
    port: int

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("NETPULSE_METRICS_HOST must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("NETPULSE_METRICS_PORT must be in the range 1..65535")

    @classmethod
    def from_env(cls, default_port: int) -> MetricsHttpConfig:
        """Load the common metrics settings, disabled unless explicitly enabled."""
        enabled_value = os.getenv("NETPULSE_METRICS_ENABLED", "false").strip().lower()
        if enabled_value == "true":
            enabled = True
        elif enabled_value == "false":
            enabled = False
        else:
            raise ValueError("NETPULSE_METRICS_ENABLED must be true or false")

        port_value = os.getenv("NETPULSE_METRICS_PORT", str(default_port))
        try:
            port = int(port_value)
        except ValueError as error:
            raise ValueError("NETPULSE_METRICS_PORT must be an integer") from error

        return cls(
            enabled=enabled,
            host=os.getenv("NETPULSE_METRICS_HOST", "127.0.0.1"),
            port=port,
        )


class MetricsServer:
    """Idempotently own the official Prometheus WSGI server and thread."""

    def __init__(self, config: MetricsHttpConfig, registry: CollectorRegistry) -> None:
        self._config = config
        self._registry = registry
        self._server: WSGIServer | None = None
        self._thread: Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start metrics serving when enabled, surfacing any bind failure."""
        if not self._config.enabled:
            return
        with self._lock:
            if self._server is not None:
                return
            server, thread = start_http_server(
                self._config.port,
                addr=self._config.host,
                registry=self._registry,
            )
            self._server = server
            self._thread = thread

    def stop(self) -> None:
        """Stop and close a running server; repeated calls are harmless."""
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)
