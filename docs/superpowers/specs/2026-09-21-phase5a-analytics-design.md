# Phase 5A — dimensional analytics design

## Intent and boundary

Provide reproducible, read-only analytics for the NetPulse local prototype:
daily reliability by observer/probe and current incident lifecycle, suitable
for Power BI. This slice does not add dashboards, Prometheus, an API, new
collectors, or physical Pi claims. Those remain separate roadmap gates.

## Source decision

Use deduplicated PostgreSQL operational tables as the exact fact source:
`network_measurements`, `service_checks`, `agents`, `endpoints`, and
`network_incidents`. Do not use Spark `network_window_metrics` for exact
reconciliation: that processor applies an event-time watermark, uses
approximate percentiles, and does not deduplicate source event IDs before its
window aggregation. Kafka replay or late arrivals could therefore make it
diverge from the ingestor's event-ID-deduplicated operational tables.

## Model and grains

- `dim_agent`: one row per operational `agent_id`, with current role/display
  attributes (Type 1 update).
- `dim_endpoint`: one row per `endpoint_id`, with current type/display
  attributes (Type 1 update).
- `dim_date`: one row per UTC calendar day appearing in a fact. UTC dates are
  derived from `event_time`, never the host's local timezone.
- `dim_probe`: one row per `(source_kind, probe_type)`, where source kind is
  `network_measurement` or `service_check` and probe type is the existing
  measurement/check type.
- `fact_reliability_daily`: one row per UTC date, agent, endpoint, and probe.
  Store total, successful, and failed observation counts, plus applicable
  latency and packet-loss sums/counts. Nullable metrics mean “not measured,”
  not zero. The natural grain has a unique database constraint; a rerun must
  replace prior aggregates for the requested dates.
- `fact_incident`: one row per `incident_id`, reflecting the latest
  `network_incidents` lifecycle revision, start/end time, status, type,
  severity, confidence, duration, and rule version.
- Separate incident-agent and incident-endpoint bridge tables hold the
  affected arrays. Joining both bridges into the same aggregate is prohibited
  because it multiplies incidents across agents and endpoints.

Network reliability is probe success rate, not an availability SLA. Service
checks contribute a separate probe class. Speed tests and heartbeats are
excluded from this first daily reliability fact because their cadence and
meaning are different; the warehouse documentation must state that limit.

## Batch behavior

The analytics job accepts either an inclusive `--from-date YYYY-MM-DD` and
`--through-date YYYY-MM-DD` pair or `--all` for backfill. It executes in a
single PostgreSQL transaction at a consistent source snapshot, takes an
advisory lock to prevent concurrent replacement, upserts dimensions, rebuilds
all daily fact rows in the selected UTC date range, and refreshes the full
current incident fact/bridges. Rebuilding a selected date must clear stale
facts even if its source rows have disappeared. Any failure rolls back the
entire run; a job-run record is committed only on success.

The inclusive range is explicit so a late event can be incorporated by
rerunning its historical date. The job does not silently promise automatic
late-data backfill. The default command may choose a documented recent window
for demos, but `--all` and explicit date ranges must remain available.

## Read interface

Create stable, read-only SQL views for daily probe reliability and incident
summaries. Views expose plain columns with UTC timestamps, counts, and rates;
they do not require Power BI to parse JSON. Rate denominators are guarded for
zero counts. A restricted reporting role may SELECT from views but cannot
mutate operational or analytics tables. Connection details remain local and
uncommitted.

## Acceptance and safety

Tests must prove: duplicate `event_id` replay leaves counts unchanged; a
historical late event changes only the rerun date; source deletion/empty
range removes stale facts; UTC midnight/DST boundaries use UTC; incident
revision/resolution updates the same fact; multi-agent/endpoint bridges do
not inflate incident counts; injected batch failure rolls back facts and job
record; reporting credentials cannot write. Reconcile source/fact totals and
incident counts in a Docker-backed integration test. Run migration SQL checks,
unit/contract tests, lint, typecheck, and Compose acceptance before marking
Phase 5A complete. Record exact outputs and any skipped checks.

## Roles and handoff

The data engineer owns schema, batch job, views, and focused tests. The
platform/Pi engineer owns only Compose/script packaging assigned by the lead.
The independent verifier reviews grain, replay, transactions, role grants,
and claims without writing files. The lead integrates and performs final
verification. Physical Pi work may proceed separately and does not gate this
software slice.
