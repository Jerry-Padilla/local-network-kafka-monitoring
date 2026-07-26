"""Validated environment configuration for the streaming processor."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, cast

TriggerMode = Literal["processing-time", "available-now"]


@dataclass(frozen=True, slots=True)
class StreamingConfig:
    bootstrap_servers: str
    source_topic: str
    starting_offsets: Literal["earliest", "latest"]
    fail_on_data_loss: bool
    checkpoint_root: str
    database_url: str
    watermark_delay: str
    trigger_mode: TriggerMode
    trigger_interval: str
    query_name: str
    shuffle_partitions: int
    maximum_output_rows_per_batch: int

    @classmethod
    def from_env(cls) -> StreamingConfig:
        """Load allowlisted settings and reject unsafe or nonsensical values."""
        starting_offsets = os.getenv("NETPULSE_STREAM_STARTING_OFFSETS", "earliest")
        if starting_offsets not in {"earliest", "latest"}:
            raise ValueError("NETPULSE_STREAM_STARTING_OFFSETS must be earliest or latest")

        trigger_mode = os.getenv("NETPULSE_STREAM_TRIGGER_MODE", "processing-time")
        if trigger_mode not in {"processing-time", "available-now"}:
            raise ValueError(
                "NETPULSE_STREAM_TRIGGER_MODE must be processing-time or available-now"
            )

        checkpoint_root = os.getenv(
            "NETPULSE_STREAM_CHECKPOINT_ROOT",
            "/var/lib/netpulse-streaming/checkpoints",
        )
        if not PurePosixPath(checkpoint_root).is_absolute():
            raise ValueError("NETPULSE_STREAM_CHECKPOINT_ROOT must be an absolute path")

        shuffle_partitions = int(os.getenv("NETPULSE_STREAM_SHUFFLE_PARTITIONS", "6"))
        maximum_rows = int(os.getenv("NETPULSE_STREAM_MAXIMUM_OUTPUT_ROWS", "10000"))
        if shuffle_partitions < 1:
            raise ValueError("NETPULSE_STREAM_SHUFFLE_PARTITIONS must be positive")
        if maximum_rows < 1:
            raise ValueError("NETPULSE_STREAM_MAXIMUM_OUTPUT_ROWS must be positive")

        return cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"),
            source_topic=os.getenv(
                "NETPULSE_STREAM_SOURCE_TOPIC",
                "network.measurements.raw.v1",
            ),
            starting_offsets=cast(Literal["earliest", "latest"], starting_offsets),
            fail_on_data_loss=_parse_bool(os.getenv("NETPULSE_STREAM_FAIL_ON_DATA_LOSS", "true")),
            checkpoint_root=checkpoint_root,
            database_url=os.getenv(
                "NETPULSE_DATABASE_URL",
                "postgresql://netpulse_app:change-me-local-app@localhost:5432/netpulse",
            ),
            watermark_delay=os.getenv("NETPULSE_STREAM_WATERMARK_DELAY", "15 minutes"),
            trigger_mode=cast(TriggerMode, trigger_mode),
            trigger_interval=os.getenv("NETPULSE_STREAM_TRIGGER_INTERVAL", "10 seconds"),
            query_name=os.getenv("NETPULSE_STREAM_QUERY_NAME", "netpulse-window-metrics-v1"),
            shuffle_partitions=shuffle_partitions,
            maximum_output_rows_per_batch=maximum_rows,
        )


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid Boolean value: {value!r}")
