# NetPulse local architecture

## Components

- The simulator models fabricated wired and Wi-Fi agents. It validates every
  normal event before publication and keys Kafka records by `agent_id`.
- The physical agent runs collectors independently, validates events, and
  writes SQLite before attempting Kafka publication. Only delivery callbacks
  mark outbox records acknowledged.
- Kafka runs as one local KRaft broker. Topic creation is explicit and
  idempotent; auto-creation is disabled.
- The event ingestor validates untrusted records, checks configured agent and
  endpoint references, persists operational data, publishes validated
  measurements or dead letters, and manually commits source offsets.
- The Spark processor independently consumes raw measurements, separates
  invalid rows, applies event-time watermarks, maintains four window sizes,
  checkpoints state, and upserts curated PostgreSQL aggregates.
- PostgreSQL retains a JSONB copy of valid input plus typed operational tables.
  Alembic owns schema evolution.

```mermaid
sequenceDiagram
    participant A as Agent collector
    participant Q as SQLite outbox
    participant K as Kafka raw topic
    participant I as Event ingestor
    participant P as PostgreSQL
    participant O as Valid or DLQ topic
    participant S as Spark streaming

    A->>Q: insert validated event
    Q->>K: produce(key=agent_id, original JSON)
    K-->>Q: delivery acknowledgement
    K->>I: poll(topic, partition, offset)
    I->>I: decode + validate contract/references
    alt valid
        I->>P: transaction: raw + typed ON CONFLICT
        P-->>I: committed
        I->>O: publish validated measurement
    else invalid
        I->>P: upsert processing failure evidence
        P-->>I: committed
        I->>O: publish dead-letter record
        I->>P: record DLQ acknowledgement
    end
    O-->>I: Kafka acknowledgement
    I->>K: commit source offset
    K->>S: raw measurement offsets
    S->>S: parse + watermark + window
    S->>P: upsert aggregates or stream rejects
    S->>S: checkpoint offsets and state
```

If processing fails, the consumer seeks to the same offset and retries with
bounded exponential backoff and jitter. After the configured attempt limit it
stops without committing, allowing an operator to repair the dependency and
restart from the failed offset.

## Kafka topics

All local topics use three partitions, replication factor one, delete cleanup,
and `agent_id` keys where the source has an agent. Ordering is guaranteed only
within one key/partition.

| Topic | Purpose | Retention |
|---|---|---:|
| `network.measurements.raw.v1` | Untrusted ping/Wi-Fi input | 7 days |
| `network.measurements.valid.v1` | Validated measurement output | 7 days |
| `network.service-checks.raw.v1` | DNS/HTTP input | 7 days |
| `network.speed-tests.raw.v1` | Low-frequency throughput input | 30 days |
| `network.agent-heartbeats.v1` | Agent runtime metadata | 7 days |
| `network.incidents.v1` | Reserved for Phase 4 incidents | 30 days |
| `network.dead-letter.v1` | Invalid input with source coordinates | 30 days |
| `network.processing-metrics.v1` | Reserved for pipeline metrics | 7 days |

The ingestor group is `netpulse-ingestion-v1`. Spark uses checkpoint-owned
consumer progress with a `netpulse-window-metrics-v1` group prefix. Replays use a new explicit
consumer group or reset this group’s offsets after confirming downstream
deduplication behavior.

## Operational database

`raw_events` is the durable compatibility record and has unique constraints on
both `event_id` and source topic/partition/offset. Typed tables use `event_id`
as a primary and foreign key:

```mermaid
erDiagram
    AGENTS ||--o{ RAW_EVENTS : produces
    RAW_EVENTS ||--o| NETWORK_MEASUREMENTS : specializes
    RAW_EVENTS ||--o| SERVICE_CHECKS : specializes
    RAW_EVENTS ||--o| SPEED_TESTS : specializes
    RAW_EVENTS ||--o| AGENT_HEARTBEATS : specializes
    ENDPOINTS ||--o{ NETWORK_MEASUREMENTS : targets
    ENDPOINTS ||--o{ SERVICE_CHECKS : targets
    AGENTS ||--o{ NETWORK_WINDOW_METRICS : summarizes
    ENDPOINTS ||--o{ NETWORK_WINDOW_METRICS : groups
```

`processing_failures` stores original bytes, validation details, attempts, and
dead-letter publication time. It deliberately remains separate from valid raw
events.

`network_window_metrics` uses the window bounds, window size, agent, endpoint,
and measurement type as its replay-safe primary key.
`stream_processing_failures` uses source topic/partition/offset uniqueness.
`streaming_query_batches` records completed sink batches.

## Reliability boundary

Kafka and PostgreSQL do not participate in one atomic transaction. A replay
after database commit can republish validated output. Database writes are
idempotent; future Spark and classifier consumers must deduplicate `event_id`.
Producer idempotence reduces duplicate retries within one producer session but
does not change the end-to-end guarantee.

Spark checkpoints make its Kafka progress and state restartable, while
PostgreSQL conflict keys make replayed sink batches idempotent. They are not one
atomic transaction, so the repository does not extend Spark's checkpoint
guarantees into an unsupported end-to-end exactly-once claim.

The physical agent adds another reliability boundary before Kafka. Collection
continues while Kafka is unavailable, pending events retain their original
timestamps, and a delivery acknowledgement can be lost during a crash. This is
also at-least-once delivery; downstream `event_id` deduplication remains
mandatory.
