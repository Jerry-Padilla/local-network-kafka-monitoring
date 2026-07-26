"""Spark Structured Streaming application entry point."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from netpulse_streaming.config import StreamingConfig
from netpulse_streaming.sink import PostgresStreamingSink
from netpulse_streaming.transformations import aggregate_measurements, split_measurements


def build_spark(config: StreamingConfig) -> Any:
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder.appName(config.query_name)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", str(config.shuffle_partitions))
        .config("spark.streaming.stopGracefullyOnShutdown", "true")
        .getOrCreate()
    )


def build_kafka_source(spark: Any, config: StreamingConfig) -> Any:
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", config.bootstrap_servers)
        .option("subscribe", config.source_topic)
        .option("startingOffsets", config.starting_offsets)
        .option("failOnDataLoss", str(config.fail_on_data_loss).lower())
        .option("groupIdPrefix", f"{config.query_name}-source-v1")
        .load()
    )


def _start_query(
    frame: Any,
    writer: Any,
    checkpoint: Path,
    query_name: str,
    config: StreamingConfig,
    output_mode: str,
) -> Any:
    stream = (
        frame.writeStream.queryName(query_name)
        .outputMode(output_mode)
        .option("checkpointLocation", str(checkpoint))
        .foreachBatch(writer)
    )
    if config.trigger_mode == "available-now":
        stream = stream.trigger(availableNow=True)
    else:
        stream = stream.trigger(processingTime=config.trigger_interval)
    return stream.start()


def run(config: StreamingConfig) -> None:
    from netpulse_contracts.logging import configure_logging

    configure_logging("netpulse-stream-processor")
    logger = structlog.get_logger()
    spark = build_spark(config)
    spark.sparkContext.setLogLevel("WARN")
    source = build_kafka_source(spark, config)
    valid, invalid = split_measurements(source)
    aggregates = aggregate_measurements(valid, config.watermark_delay)
    sink = PostgresStreamingSink(config.database_url, config.maximum_output_rows_per_batch)

    checkpoint_root = Path(config.checkpoint_root)
    metrics_query = _start_query(
        aggregates,
        sink.write_metrics,
        checkpoint_root / "metrics",
        f"{config.query_name}-metrics",
        config,
        "update",
    )
    invalid_query = _start_query(
        invalid,
        sink.write_failures,
        checkpoint_root / "invalid",
        f"{config.query_name}-invalid",
        config,
        "append",
    )
    queries = (metrics_query, invalid_query)
    logger.info(
        "streaming_queries_started",
        source_topic=config.source_topic,
        trigger_mode=config.trigger_mode,
        checkpoint_root=config.checkpoint_root,
    )
    try:
        while any(query.isActive for query in queries):
            for query in queries:
                progress = query.lastProgress
                if progress:
                    logger.info(
                        "streaming_progress",
                        query_name=query.name,
                        batch_id=progress.get("batchId"),
                        input_rows=progress.get("numInputRows"),
                        input_rate=progress.get("inputRowsPerSecond"),
                        processing_rate=progress.get("processedRowsPerSecond"),
                        event_time=progress.get("eventTime"),
                        state_operators=progress.get("stateOperators"),
                    )
            time.sleep(2)
        for query in queries:
            query.awaitTermination()
    finally:
        for query in queries:
            if query.isActive:
                query.stop()
        spark.stop()
        logger.info("streaming_queries_stopped")


def main() -> None:
    run(StreamingConfig.from_env())
