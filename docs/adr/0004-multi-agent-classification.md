# ADR 0004: deterministic database-backed incident correlation

## Status

Accepted for Phase 4.

## Decision

Run deterministic rules in a small Python service over bounded PostgreSQL
operational observations. Persist lifecycle state and a serialized incident
outbox in one database transaction, then publish the outbox to Kafka with
acknowledgement before marking it delivered.

## Rationale

Measurements, service checks, and heartbeats arrive on separate Kafka topics
and partitions. PostgreSQL already contains validated, typed event-time records
and supports a transparent bounded correlation query. A deterministic service
is easier to test and explain than embedding stateful business rules inside the
initial Spark aggregation job.

The outbox does not create end-to-end exactly-once delivery. It prevents silent
loss between state persistence and Kafka publication; an acknowledgement lost
during a crash can cause a duplicate stable event ID.

## Consequences

- Rule evaluation depends on PostgreSQL availability and indexed event-time
  queries.
- Thresholds and observation counts are explicit and configurable.
- Incident explanations remain reproducible and evidence-bearing.
- Future learned anomaly models can propose findings without replacing the
  lifecycle or delivery boundary.
