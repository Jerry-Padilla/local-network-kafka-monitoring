# Event contracts

## Version 1 envelope

Every event includes `event_id`, `event_type`, `schema_version`, `agent_id`,
`agent_role`, `event_time`, `published_time`, `sequence_number`,
`correlation_id`, and `source_version`.

- IDs are UUID strings. `event_id` is the global deduplication key.
- Timestamps must be timezone-aware UTC ISO 8601. `event_time` describes when
  the agent observed the condition; `published_time` describes serialization
  into the local outbox, not the later Kafka acknowledgement time.
- Sequence numbers are nonnegative. The physical agent persists its sequence
  in SQLite across restarts; simulator sequences are scoped to a run.
- `schema_version` is an integer wire-contract version. Phase 1 accepts only 1.
- `source_version` is the semantic version of the producing software.
- `correlation_id` is explicitly nullable; other fields are nullable only where
  the event-specific schema says so.

## Units

- Latency, jitter, and durations: milliseconds
- Packet loss and utilization: percentage from 0 through 100
- Throughput: megabits per second
- Signal strength: dBm
- Uptime: seconds
- CPU temperature: degrees Celsius

Negative durations/throughput and out-of-range percentages or signal strength
are invalid. High but plausible latency and packet loss remain valid telemetry;
anomalies are not data-quality failures.

## Compatibility policy

- Producers may add optional fields without incrementing `schema_version`.
- Consumers preserve and ignore unknown additive fields.
- Removing a field, changing a field’s type/unit/meaning, or making an optional
  field required needs a new major schema version and a parallel versioned topic
  or documented migration.
- Producers must continue emitting all version 1 required fields.
- Consumers reject unsupported schema versions to the dead-letter path rather
  than guessing.
- A field that is absent differs from a field explicitly set to null.

The JSON schemas in `schemas/` are the language-neutral contract. Pydantic
models in `packages/contracts` are the Python implementation. Contract tests
validate representative producer output against both.

Phase 2 collectors use allowed additive fields for target address, Wi-Fi
interface, protected SSID/BSSID, frequency, and link bitrate. These fields
remain optional so Phase 1 consumers continue to accept the same version 1
contract.

## Topic routing

- `network.measurement` → `network.measurements.raw.v1`
- `network.service_check` → `network.service-checks.raw.v1`
- `network.speed_test` → `network.speed-tests.raw.v1`
- `network.agent_heartbeat` → `network.agent-heartbeats.v1`
- `network.incident` → `network.incidents.v1`

Unknown event types have no default topic.
