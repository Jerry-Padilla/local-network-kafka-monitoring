"""Spark parsing, validation, and event-time aggregate transformations."""

from __future__ import annotations

from typing import Any

WINDOWS = (
    ("1 minute", 60),
    ("5 minutes", 300),
    ("15 minutes", 900),
    ("1 day", 86_400),
)


def measurement_schema() -> Any:
    """Return the additive-compatible schema projected from raw JSON."""
    from pyspark.sql import types as T

    return T.StructType(
        [
            T.StructField("event_id", T.StringType()),
            T.StructField("event_type", T.StringType()),
            T.StructField("schema_version", T.IntegerType()),
            T.StructField("agent_id", T.StringType()),
            T.StructField("agent_role", T.StringType()),
            T.StructField("event_time", T.TimestampType()),
            T.StructField("published_time", T.TimestampType()),
            T.StructField("sequence_number", T.LongType()),
            T.StructField("correlation_id", T.StringType()),
            T.StructField("source_version", T.StringType()),
            T.StructField("measurement_type", T.StringType()),
            T.StructField("target_id", T.StringType()),
            T.StructField("success", T.BooleanType()),
            T.StructField("latency_ms", T.DoubleType()),
            T.StructField("packet_loss_pct", T.DoubleType()),
            T.StructField("jitter_ms", T.DoubleType()),
            T.StructField("signal_dbm", T.DoubleType()),
            T.StructField("connected", T.BooleanType()),
            T.StructField("error_class", T.StringType()),
            T.StructField("error_message", T.StringType()),
            T.StructField("_corrupt_record", T.StringType()),
        ]
    )


def split_measurements(kafka_records: Any) -> tuple[Any, Any]:
    """Parse Kafka rows and split schema-valid measurements from rejects."""
    from pyspark.sql import functions as F

    decoded = kafka_records.select(
        F.col("topic").alias("source_topic"),
        F.col("partition").alias("source_partition"),
        F.col("offset").alias("source_offset"),
        F.col("timestamp").alias("kafka_timestamp"),
        F.col("key").cast("string").alias("source_key"),
        F.col("value").alias("original_payload"),
        F.from_json(
            F.col("value").cast("string"),
            measurement_schema(),
            {
                "mode": "PERMISSIVE",
                "columnNameOfCorruptRecord": "_corrupt_record",
            },
        ).alias("event"),
    )
    event = F.col("event")
    uuid_pattern = (
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
        r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    )
    rules = (
        (event.isNull(), "malformed_json"),
        (F.col("event._corrupt_record").isNotNull(), "malformed_json"),
        (F.col("event.event_id").isNull(), "missing_or_invalid:event_id"),
        (~F.col("event.event_id").rlike(uuid_pattern), "invalid:event_id"),
        (F.col("event.event_type") != F.lit("network.measurement"), "unsupported:event_type"),
        (F.col("event.schema_version") != F.lit(1), "unsupported:schema_version"),
        (
            ~F.col("event.agent_role").isin("wired_reference", "wifi_observer"),
            "invalid:agent_role",
        ),
        (F.col("event.agent_id").isNull(), "missing:agent_id"),
        (F.col("event.event_time").isNull(), "missing_or_invalid:event_time"),
        (F.col("event.published_time").isNull(), "missing_or_invalid:published_time"),
        (
            F.col("event.sequence_number").isNull() | (F.col("event.sequence_number") < 0),
            "invalid:sequence_number",
        ),
        (F.col("event.source_version").isNull(), "missing:source_version"),
        (
            ~F.col("event.measurement_type").isin(
                "router_ping",
                "external_ping",
                "wifi_diagnostics",
            ),
            "invalid:measurement_type",
        ),
        (F.col("event.target_id").isNull(), "missing:target_id"),
        (F.col("event.success").isNull(), "missing_or_invalid:success"),
        (
            F.col("event.packet_loss_pct").isNull()
            | (F.col("event.packet_loss_pct") < 0)
            | (F.col("event.packet_loss_pct") > 100),
            "invalid:packet_loss_pct",
        ),
        (
            (~F.col("event.success")) & F.col("event.latency_ms").isNotNull(),
            "invalid:failed_latency",
        ),
        (
            (F.col("event.measurement_type") == "wifi_diagnostics")
            & F.col("event.connected").isNull(),
            "missing:connected",
        ),
        (
            F.col("source_key").isNotNull() & (F.col("source_key") != F.col("event.agent_id")),
            "invalid:agent_key",
        ),
    )
    errors = F.filter(
        F.array(*[F.when(condition, F.lit(message)) for condition, message in rules]),
        lambda item: item.isNotNull(),
    )
    classified = decoded.withColumn("validation_errors", errors)

    valid = (
        classified.where(F.size("validation_errors") == 0)
        .select(
            "source_topic",
            "source_partition",
            "source_offset",
            "kafka_timestamp",
            "event.*",
        )
        .drop("_corrupt_record")
        .withColumn("processing_time", F.current_timestamp())
        .withColumn(
            "ingestion_latency_ms",
            F.greatest(
                F.lit(0.0),
                (F.unix_millis(F.current_timestamp()) - F.unix_millis(F.col("event_time"))).cast(
                    "double"
                ),
            ),
        )
    )
    invalid = classified.where(F.size("validation_errors") > 0).select(
        "source_topic",
        "source_partition",
        "source_offset",
        "source_key",
        "original_payload",
        "validation_errors",
        F.current_timestamp().alias("failed_at"),
    )
    return valid, invalid


def aggregate_measurements(valid_measurements: Any, watermark_delay: str) -> Any:
    """Build event-time aggregates for the four documented window sizes."""
    from pyspark.sql import functions as F

    watermarked = valid_measurements.withWatermark("event_time", watermark_delay)
    aggregates: list[Any] = []
    for duration, window_size_seconds in WINDOWS:
        grouped = watermarked.groupBy(
            F.window("event_time", duration).alias("event_window"),
            "agent_id",
            "target_id",
            "measurement_type",
        ).agg(
            F.count(F.lit(1)).cast("long").alias("event_count"),
            F.sum(F.when(F.col("success"), F.lit(1)).otherwise(F.lit(0)))
            .cast("long")
            .alias("success_count"),
            F.min("latency_ms").alias("latency_min_ms"),
            F.max("latency_ms").alias("latency_max_ms"),
            F.avg("latency_ms").alias("latency_mean_ms"),
            F.stddev_pop("latency_ms").alias("latency_stddev_ms"),
            F.percentile_approx("latency_ms", [0.5, 0.95, 0.99], 10_000).alias(
                "latency_percentiles"
            ),
            F.avg("jitter_ms").alias("jitter_mean_ms"),
            F.avg("packet_loss_pct").alias("packet_loss_mean_pct"),
            F.avg("ingestion_latency_ms").alias("ingestion_latency_mean_ms"),
        )
        aggregates.append(
            grouped.select(
                F.col("event_window.start").alias("window_start"),
                F.col("event_window.end").alias("window_end"),
                F.lit(window_size_seconds).alias("window_size_seconds"),
                "agent_id",
                "target_id",
                "measurement_type",
                "event_count",
                "success_count",
                (F.col("event_count") - F.col("success_count")).alias("failure_count"),
                (F.col("success_count") * F.lit(100.0) / F.col("event_count")).alias(
                    "success_rate_pct"
                ),
                "latency_min_ms",
                "latency_max_ms",
                "latency_mean_ms",
                "latency_stddev_ms",
                F.col("latency_percentiles").getItem(0).alias("latency_p50_ms"),
                F.col("latency_percentiles").getItem(1).alias("latency_p95_ms"),
                F.col("latency_percentiles").getItem(2).alias("latency_p99_ms"),
                "jitter_mean_ms",
                "packet_loss_mean_pct",
                "ingestion_latency_mean_ms",
                F.current_timestamp().alias("calculated_at"),
            )
        )

    result = aggregates[0]
    for aggregate in aggregates[1:]:
        result = result.unionByName(aggregate)
    return result
