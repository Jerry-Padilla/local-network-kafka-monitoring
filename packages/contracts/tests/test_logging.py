from __future__ import annotations

from netpulse_contracts.logging import configure_logging


def test_logging_accepts_environment_and_explicit_levels(monkeypatch) -> None:
    monkeypatch.setenv("NETPULSE_LOG_LEVEL", "debug")

    configure_logging("contract-test")
    configure_logging("contract-test", "warning")
