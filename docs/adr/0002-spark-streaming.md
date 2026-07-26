# ADR 0002: Spark Structured Streaming for event-time curation

- Status: accepted
- Date: 2026-07-26

## Decision

Use PySpark 4.1.2 with Java 17 and the matching Scala 2.13 Kafka connector.
Run a local two-thread Spark driver in the opt-in `streaming` Compose profile.
Read the raw measurement topic, retain invalid source evidence in PostgreSQL,
apply event-time watermarks, and persist aggregate micro-batches through
bounded driver-side PostgreSQL upserts.

## Rationale

The portfolio brief explicitly requires real Structured Streaming,
watermarks, checkpoints, progress metrics, and PostgreSQL curation. Aggregate
output cardinality is small and bounded, so collecting aggregate rows in the
driver avoids per-executor database connection complexity while the hard row
limit prevents an unbounded collection.

The inspected official Spark image used Python 3.10.12. Building from the
pinned Python 3.12 base with PySpark preserves the repository runtime standard.

## Consequences

- The first run requires Maven Central access for pinned Kafka connector jars.
- State and offsets depend on persistent checkpoint compatibility with the
  query plan.
- PostgreSQL upserts make replay safe at the row key but do not make Kafka,
  Spark state, and PostgreSQL one atomic exactly-once transaction.
- Scaling beyond local aggregate cardinality would require an executor-side
  JDBC/staging design or another transactional sink.
