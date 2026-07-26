"""Durable SQLite outbox for at-least-once agent delivery."""

from __future__ import annotations

import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from netpulse_contracts.models import Event
from netpulse_contracts.topics import topic_for_event

from netpulse_agent.config import OutboxConfig

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    message_key TEXT NOT NULL,
    payload BLOB NOT NULL,
    created_at REAL NOT NULL,
    delivered_at REAL,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    last_error TEXT,
    next_attempt_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_outbox_ready
    ON outbox_events (delivered_at, next_attempt_at, created_at);
CREATE TABLE IF NOT EXISTS outbox_metadata (
    key TEXT PRIMARY KEY,
    integer_value INTEGER NOT NULL
);
INSERT OR IGNORE INTO outbox_metadata (key, integer_value)
VALUES ('sequence_number', -1);
"""


class OutboxFullError(RuntimeError):
    """The configured local storage ceiling would be exceeded."""


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    event_id: UUID
    topic: str
    message_key: str
    payload: bytes
    retry_count: int


@dataclass(frozen=True, slots=True)
class OutboxStats:
    pending: int
    delivered_retained: int
    database_bytes: int


class SQLiteOutbox:
    """Small synchronized SQLite queue; each operation owns its connection."""

    def __init__(self, config: OutboxConfig) -> None:
        self._config = config
        self._path = config.path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _storage_bytes(self) -> int:
        return sum(
            candidate.stat().st_size
            for candidate in (
                self._path,
                Path(f"{self._path}-wal"),
                Path(f"{self._path}-shm"),
            )
            if candidate.exists()
        )

    def next_sequence(self) -> int:
        """Atomically allocate a monotonically increasing local sequence."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT integer_value FROM outbox_metadata WHERE key = 'sequence_number'"
            ).fetchone()
            current = int(row[0]) if row is not None else -1
            following = current + 1
            connection.execute(
                """
                INSERT INTO outbox_metadata (key, integer_value)
                VALUES ('sequence_number', ?)
                ON CONFLICT (key) DO UPDATE SET integer_value = excluded.integer_value
                """,
                (following,),
            )
            return following

    def enqueue(self, event: Event, now: float | None = None) -> bool:
        """Persist a validated event before it becomes eligible for publication."""
        payload = event.model_dump_json().encode()
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._storage_bytes() + len(payload) > self._config.maximum_bytes:
                raise OutboxFullError(
                    f"outbox maximum of {self._config.maximum_bytes} bytes would be exceeded"
                )
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO outbox_events (
                    event_id, topic, message_key, payload, created_at, next_attempt_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_id),
                    topic_for_event(event.event_type),
                    event.agent_id,
                    payload,
                    timestamp,
                    timestamp,
                ),
            )
            return cursor.rowcount == 1

    def ready(self, now: float | None = None) -> list[OutboxRecord]:
        """Return a bounded ordered batch eligible for a delivery attempt."""
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, topic, message_key, payload, retry_count
                FROM outbox_events
                WHERE delivered_at IS NULL AND next_attempt_at <= ?
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (timestamp, self._config.batch_size),
            ).fetchall()
        return [
            OutboxRecord(
                event_id=UUID(str(row[0])),
                topic=str(row[1]),
                message_key=str(row[2]),
                payload=bytes(row[3]),
                retry_count=int(row[4]),
            )
            for row in rows
        ]

    def mark_delivered(self, event_id: UUID, now: float | None = None) -> None:
        """Mark one event only after its Kafka delivery callback succeeds."""
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE outbox_events
                SET delivered_at = ?, last_error = NULL
                WHERE event_id = ? AND delivered_at IS NULL
                """,
                (timestamp, str(event_id)),
            )

    def mark_failed(
        self,
        record: OutboxRecord,
        error: str,
        now: float | None = None,
        random_value: float | None = None,
    ) -> float:
        """Record failure and schedule bounded exponential backoff with jitter."""
        timestamp = time.time() if now is None else now
        retry_count = record.retry_count + 1
        exponential = self._config.retry_base_seconds * (2 ** min(record.retry_count, 20))
        base_delay = min(self._config.retry_max_seconds, exponential)
        jitter_fraction = random.random() if random_value is None else random_value
        delay = base_delay + base_delay * 0.25 * min(1.0, max(0.0, jitter_fraction))
        next_attempt = timestamp + delay
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE outbox_events
                SET retry_count = ?, last_error = ?, next_attempt_at = ?
                WHERE event_id = ? AND delivered_at IS NULL
                """,
                (retry_count, error[:1024], next_attempt, str(record.event_id)),
            )
        return float(next_attempt)

    def prune_acknowledged(self, now: float | None = None) -> int:
        """Delete old acknowledged rows; undelivered rows are never pruned."""
        timestamp = time.time() if now is None else now
        cutoff = timestamp - self._config.acknowledged_retention_seconds
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM outbox_events
                WHERE delivered_at IS NOT NULL AND delivered_at <= ?
                """,
                (cutoff,),
            )
            return cursor.rowcount

    def depth(self) -> int:
        """Count undelivered records."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT count(*) FROM outbox_events WHERE delivered_at IS NULL"
            ).fetchone()
            return int(row[0]) if row is not None else 0

    def stats(self) -> OutboxStats:
        """Return queue and storage counters without event payloads."""
        with self._connect() as connection:
            pending = int(
                connection.execute(
                    "SELECT count(*) FROM outbox_events WHERE delivered_at IS NULL"
                ).fetchone()[0]
            )
            delivered = int(
                connection.execute(
                    "SELECT count(*) FROM outbox_events WHERE delivered_at IS NOT NULL"
                ).fetchone()[0]
            )
        return OutboxStats(pending, delivered, self._storage_bytes())
