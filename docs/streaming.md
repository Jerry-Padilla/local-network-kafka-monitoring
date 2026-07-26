# Spark Structured Streaming

## Scope

Phase 3 reads `network.measurements.raw.v1` independently of the Phase 1
ingestor. It parses the version 1 measurement envelope, retains malformed or
invalid source coordinates in `stream_processing_failures`, applies a
15-minute event-time watermark, and upserts curated aggregates into
`network_window_metrics`.

Service checks, speed tests, heartbeats, incident candidates, and incident
classification remain outside this job. They are not silently represented as
completed streaming features.

## Windows and metrics

The query maintains tumbling 1-minute, 5-minute, 15-minute, and daily windows
grouped by:

- `agent_id`;
- `target_id`;
- `measurement_type`.

Each row contains event, success, and failure counts; success percentage;
minimum, maximum, mean, population standard deviation, approximate P50, P95,
and P99 latency; mean reported jitter; mean packet loss; and mean event-time
ingestion latency.

Percentiles use Spark `percentile_approx` with accuracy `10000`. Jitter is the
mean of the agent-reported `jitter_ms` field, not a second derivation from
adjacent raw samples. Event-time latency is clamped to zero for future-dated
clock-drift samples rather than being reported as negative.

## Validation and late data

Spark projects known fields from JSON while allowing unknown additive fields.
It rejects malformed JSON, missing or mistyped required values, unsupported
schema versions, invalid enum/range values, failed records that report latency,
Wi-Fi records without connection state, and Kafka keys that disagree with
`agent_id`.

Structurally valid high latency and packet loss remain valid data. They are
aggregated normally and are not classified as incidents in Phase 3.

The watermark is relative to the greatest event time observed across Kafka
partitions. Spark may accept some records older than the configured threshold;
records dropped by the state store are visible in structured query progress.
The watermark bounds aggregate state, not Kafka retention.

## Recovery and delivery semantics

`spark-checkpoints` stores Kafka offsets, query metadata, watermarks, and state
stores. `spark-ivy-cache` stores the pinned Kafka connector dependencies.
Restarting with the same query plan and checkpoint resumes from recorded
offsets.

Each aggregate is written through `foreachBatch` with a database primary key
covering its window and dimensions. Rejects are unique by source
topic/partition/offset. Both sinks use PostgreSQL `ON CONFLICT`, so a replayed
micro-batch updates the same row.

Spark checkpointing and deterministic `batch_id` values reduce replay risk,
but Kafka, checkpoints, and PostgreSQL do not share one atomic transaction.
NetPulse therefore does not claim end-to-end exactly-once delivery.

The driver collects only aggregate/reject output rows, not raw telemetry. A
configurable hard limit defaults to 10,000 output rows per micro-batch and
fails the query visibly if exceeded.

## Commands

```text
./scripts/netpulse.ps1 stream-build
./scripts/netpulse.ps1 stream-run
./scripts/netpulse.ps1 stream-once
./scripts/netpulse.ps1 stream-verify
```

The POSIX and Make equivalents use the same command names. `stream-verify`
publishes deterministic valid and malformed traffic, executes an
`available-now` run, and exits nonzero unless all four window sizes, both
agents, reject evidence, and aggregate-key uniqueness are present.

The first run needs access to Maven Central for the pinned Spark Kafka
connector. Later runs reuse the named Ivy cache.
