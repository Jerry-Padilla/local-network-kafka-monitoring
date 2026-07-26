"""Privacy transformations for identifiers collected on home networks."""

from __future__ import annotations

import hashlib
from typing import Literal

from netpulse_agent.config import PrivacyConfig


def protect_identifier(
    value: str | None,
    mode: Literal["omit", "hash", "plain"],
    salt: str,
) -> str | None:
    """Omit, hash, or retain an explicitly configured identifier."""
    if value is None or mode == "omit":
        return None
    if mode == "plain":
        return value
    digest = hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()
    return f"sha256:{digest}"


def protect_wifi_identifiers(
    ssid: str | None,
    bssid: str | None,
    config: PrivacyConfig,
) -> tuple[str | None, str | None]:
    """Apply independent SSID and BSSID policies."""
    return (
        protect_identifier(ssid, config.ssid, config.hash_salt),
        protect_identifier(bssid, config.bssid, config.hash_salt),
    )
