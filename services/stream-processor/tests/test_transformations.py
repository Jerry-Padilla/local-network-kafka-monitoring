from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from netpulse_streaming.transformations import aggregate_measurements, split_measurements


@pytest.fixture(scope="module")
def spark() -> Any:
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("netpulse-transform-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def payload(*, success: bool = True, packet_loss_pct: float = 0.0) -> bytes:
    timestamp = "2026-01-01T00:00:10Z"
    return json.dumps(
        {
            "event_id": str(uuid4()),
            "event_type": "network.measurement",
            "schema_version": 1,
            "agent_id": "network-agent-wifi-01",
            "agent_role": "wifi_observer",
            "event_time": timestamp,
            "published_time": timestamp,
            "sequence_number": 1,
            "correlation_id": None,
            "source_version": "0.2.0",
            "measurement_type": "external_ping",
            "target_id": "public-dns-a",
            "success": success,
            "latency_ms": 25.0 if success else None,
            "packet_loss_pct": packet_loss_pct,
            "jitter_ms": 2.0 if success else None,
            "future_field": "allowed",
        }
    ).encode()


def kafka_frame(spark: Any, values: list[bytes]) -> Any:
    from pyspark.sql import types as T

    schema = T.StructType(
        [
            T.StructField("key", T.BinaryType(), True),
            T.StructField("value", T.BinaryType(), True),
            T.StructField("topic", T.StringType(), False),
            T.StructField("partition", T.IntegerType(), False),
            T.StructField("offset", T.LongType(), False),
            T.StructField("timestamp", T.TimestampType(), False),
        ]
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        (
            b"network-agent-wifi-01",
            value,
            "network.measurements.raw.v1",
            index % 3,
            index,
            now,
        )
        for index, value in enumerate(values)
    ]
    return spark.createDataFrame(rows, schema)


def test_spark_parser_splits_valid_and_malformed_rows(spark: Any) -> None:
    valid, invalid = split_measurements(kafka_frame(spark, [payload(), b'{"broken":']))

    assert valid.count() == 1
    rejected = invalid.collect()
    assert len(rejected) == 1
    assert "malformed_json" in rejected[0].validation_errors


def test_event_time_aggregates_include_all_documented_windows(spark: Any) -> None:
    valid, _ = split_measurements(
        kafka_frame(spark, [payload(), payload(success=False, packet_loss_pct=100.0)])
    )

    rows = aggregate_measurements(valid, "15 minutes").collect()

    assert {row.window_size_seconds for row in rows} == {60, 300, 900, 86_400}
    assert all(row.event_count == 2 for row in rows)
    assert all(row.success_count == 1 for row in rows)
    assert all(row.failure_count == 1 for row in rows)
    assert all(row.success_rate_pct == 50.0 for row in rows)
    assert all(row.packet_loss_mean_pct == 50.0 for row in rows)
