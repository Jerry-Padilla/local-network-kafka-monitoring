# Phase 1 completion report

## Outcome

NetPulse Phase 1 passed the complete feasible local acceptance suite on
2026-07-26 UTC. The validated vertical slice is:

```text
deterministic two-agent simulator
  -> Kafka 4.2.0
  -> validation, deduplication, and dead-letter handling
  -> PostgreSQL 17.10
```

The Raspberry Pi agent and all later-phase components remain gated and were not
started.

## Validated environment

- Windows host with Docker Desktop 4.83.0
- Docker Engine 29.6.2, Linux/amd64, `overlay2` storage
- Docker Compose 5.3.1
- Python 3.12.10 in the test and service images
- Apache Kafka 4.2.0 in single-node KRaft mode
- PostgreSQL 17.10 (`postgres:17.10-bookworm`)

The workstation has Python 3.13 rather than 3.12, so the authoritative runtime
test was the pinned Python 3.12.10 container suite.

## Automated checks

| Check | Observed result |
|---|---|
| `ruff format --check .` | 40 files already formatted |
| `ruff check --no-cache .` | All checks passed |
| `mypy` | No issues in 20 source files |
| Docker unit/contract Pytest suite | 53 passed, 1 deselected |
| Docker unit/contract coverage | 88.61%; required 80% reached |
| Docker integration Pytest suite | 1 passed, 53 deselected |
| Alembic offline SQL generation | Passed |
| Live `alembic upgrade head` rerun | Passed at migration head |
| Compose configuration validation | Passed |
| Service/test image builds | Passed |
| PowerShell parser check | Passed |
| Linux `bash -n` for both shell scripts | Passed in the Kafka image |
| Repository trailing-whitespace scan | Passed |

The integration test published valid, malformed, and repeated-ID records. It
confirmed one database row for the repeated `event_id`, durable failure
evidence, and an acknowledged dead-letter publication.

## Live stack evidence

Topic reconciliation was rerun successfully. All eight `network.*` topics had
three partitions and replication factor one. Measurement, service-check,
heartbeat, validated-measurement, and processing-metric topics reported
seven-day retention. Speed-test, incident, and dead-letter topics reported
30-day retention.

The documented PowerShell demo completed with:

```text
healthy: 10 rounds, 110 records sent
wifi-degradation: 5 rounds, 55 records sent
raw events: 209
wired agent events: 95
wireless agent events: 114
typed measurements: 95
duplicate event IDs: 0
Phase 1 database invariants passed
```

The malformed verification completed with 24 records sent and the database
invariants passed. After all acceptance drills, the final live query reported:

```text
raw_events=275
network_measurements=125
valid_anomalies=10
processing_failures=5
dlq_marked=5
duplicate_ids=0
```

Kafka dead-letter offsets totaled five records. The ten high-latency or
packet-loss measurements remained in the normal typed measurement table,
confirming that schema-valid anomalies are not dead-lettered.

## Replay and outage observations

A controlled replay stopped the ingestor, rewound one source offset, and
restarted it. PostgreSQL remained at 231 raw rows and 105 measurement rows,
while the validated Kafka output advanced by one record. This demonstrates the
documented behavior: database deduplication is effective, but downstream Kafka
records can repeat under at-least-once delivery.

During a PostgreSQL interruption, one simulator round added 11 Kafka records.
Consumer offsets did not advance and lag increased to 11. After PostgreSQL
restarted, lag returned to zero and all 11 records appeared in PostgreSQL.

During a Kafka interruption, a queued 11-record round remained absent from
PostgreSQL while the broker was unavailable. After Kafka restarted, consumer
lag returned to zero and the raw-event count increased from 242 to 253.

At the final inspection, Kafka, PostgreSQL, and the event ingestor were all
healthy. The deployable simulator and event-ingestor images ran as the
unprivileged `netpulse` user.

## Not executed or not claimed

- GitHub-hosted Actions were not triggered from this local workspace; their
  equivalent quality, build, and integration commands passed locally.
- No real Raspberry Pi, network probe hardware, or SQLite outbox was tested.
- No multi-broker, multi-node, performance, capacity, availability, or
  production-security claim is made.
- Spark, anomaly classification, dashboards, API, Kubernetes, RAG, and MCP
  remain later-phase work.
