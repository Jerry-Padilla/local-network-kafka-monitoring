# Tableau Public dashboard

NetPulse can export four privacy-reduced CSV datasets for an optional Tableau
Public workbook. Tableau is a downstream reporting surface: it is not required
to run NetPulse, and it never connects to Kafka or PostgreSQL.

## Generate synthetic demo data

The safest portfolio workflow uses the deterministic simulator. Its identifiers
and observations are synthetic and must not be presented as production results.

PowerShell:

```powershell
./scripts/netpulse.ps1 up
./scripts/netpulse.ps1 demo
./scripts/netpulse.ps1 classifier-once
./scripts/netpulse.ps1 analytics-all
./scripts/netpulse.ps1 tableau-export
```

POSIX:

```bash
make up
make demo
make classifier-once
make analytics-all
make tableau-export
```

The exporter reads one repeatable-read snapshot of the existing reporting views
and atomically replaces `tableau_exports/`. If a query, transformation, or file
write fails, the prior valid directory remains in place. Running the exporter
again is safe; it replaces the dataset rather than appending rows.

The export does not refresh analytics facts. Run `analytics-all` first whenever
the workbook should include newly ingested or classified demo events.

## Dataset dictionary

All percentages use a 0-to-100 scale. Latency and duration use milliseconds.
Timestamps are UTC ISO 8601 values ending in `Z`. An empty CSV field means the
source metric was unavailable; it does not mean zero.

### `daily_reliability.csv`

Grain: one row per UTC date, pseudonymous agent, source kind, and measurement
type. Endpoint-level facts are combined with weighted source numerators and
denominators before export.

| Column | Meaning |
|---|---|
| `date_utc` | Observation date in UTC. |
| `agent_key` | Stable export-only pseudonym, not the source agent ID. |
| `agent_role` | Supported role such as `wired_reference` or `wifi_observer`. |
| `source_kind` | `network_measurement` or `service_check`. |
| `measurement_type` | Probe/check type. |
| `total_probes` | Deduplicated observations in the row grain. |
| `successful_probes` | Successful observations. |
| `failed_probes` | Failed observations. |
| `success_rate_pct` | `100 × successful_probes / total_probes`. |
| `average_latency_ms` | Weighted mean of measured latency, or empty. |
| `average_packet_loss_pct` | Weighted mean packet loss, or empty. |

### `incidents.csv`

Grain: one row per current incident snapshot.

| Column | Meaning |
|---|---|
| `incident_id` | Incident UUID. |
| `incident_type` | Classifier's probable category. |
| `start_time_utc`, `end_time_utc` | Lifecycle timestamps; end is empty while active. |
| `duration_ms` | Modeled incident duration in milliseconds. |
| `status` | Current lifecycle status. |
| `severity` | Severity modeled by NetPulse. |
| `confidence_score` | Classifier confidence value as stored by NetPulse. |
| `rule_version`, `state_revision` | Rule and lifecycle revision metadata. |
| `affected_agent_count` | Count only; individual agent attribution is not exported. |
| `affected_endpoint_count` | Count only; endpoint identifiers are not exported. |

### `agent_performance.csv`

Grain: one row per pseudonymous agent, role, source kind, and measurement type
across all refreshed daily facts.

| Column | Meaning |
|---|---|
| `agent_key`, `agent_role` | Same public agent dimensions as daily reliability. |
| `source_kind`, `measurement_type` | Probe dimensions. |
| `first_observation_date`, `latest_observation_date` | Available UTC fact-date range. |
| `observation_day_count` | Count of distinct UTC observation dates. |
| `total_probes`, `successful_probes`, `failed_probes` | Period totals. |
| `success_rate_pct` | Count-derived period success rate. |
| `average_latency_ms` | Weighted period mean where latency was measured. |
| `average_packet_loss_pct` | Weighted period mean where loss was measured. |

Incident count is intentionally absent: the approved incident summary view does
not expose an individual-agent relationship.

### `pipeline_health.csv`

Grain: one point-in-time export snapshot.

| Column | Meaning |
|---|---|
| `observed_at_utc` | Snapshot timestamp. |
| `last_raw_event_received_at_utc` | Most recent raw receipt time, if any. |
| `raw_event_age_seconds` | Receipt freshness at export time. |
| `pending_dead_letter_count` | Failures awaiting dead-letter acknowledgement. |
| `stream_processing_failure_count` | Recorded streaming failures. |
| `last_stream_batch_completed_at_utc` | Most recent completed Spark batch, if any. |
| `active_incident_count` | Non-resolved incident count. |
| `pending_incident_publication_count` | Incident states awaiting Kafka acknowledgement. |

This file is not a historical time series and does not measure ingestion success
or p95 processing latency.

## Tableau data model

Connect to each CSV as a logical table. Relationships are optional:

- `daily_reliability.csv` may relate many-to-one to
  `agent_performance.csv` on `agent_key`, `source_kind`, and
  `measurement_type`.
- Do not relate `incidents.csv` to an agent. It contains counts, not entity keys.
- Keep `pipeline_health.csv` standalone because it is a single snapshot.
- Do not join tables physically merely to build one dashboard. Separate data
  sources avoid row multiplication and misleading incident counts.

For an aggregate reliability KPI, create this Tableau calculated field instead
of averaging row percentages:

```text
Probe Success Rate (%)
100 * SUM([successful_probes]) / SUM([total_probes])
```

Use `COUNTD([incident_id])` for incident count. `average_latency_ms` and
`average_packet_loss_pct` are already averages at their documented row grain;
filter to a consistent agent/source/measurement grain before comparing them.
Do not sum those fields or present a cross-grain average as an exact weighted
network-wide value.

## Recommended workbook

### Executive Network Reliability

- KPI cards: count-derived probe success rate, distinct incident count, and the
  supported average latency or packet-loss value at the selected grain.
- Line chart: `date_utc` against `Probe Success Rate (%)`.
- Optional companion lines: latency and packet loss, separated by measurement
  type rather than combined into one network-wide mean.
- Filters: date, agent key, agent role, source kind, and measurement type.

### Incident Analysis

- Bars for distinct incidents by `incident_type`.
- Time series by `start_time_utc`.
- Duration distribution using `duration_ms`.
- Pareto view: descending category count plus running percentage of distinct
  incidents.
- Detail table with status, severity, confidence, duration, affected counts,
  rule version, and revision.

These are probable classifier categories, not definitive root-cause diagnoses.

### Agent Performance

- Compare `wired_reference` and `wifi_observer`, or individual `agent_key`
  values, using period probe counts and count-derived success rate.
- Show average latency and loss only within comparable measurement types.
- Include first/latest date and observation-day count so sparse agents are not
  mistaken for fully observed agents.
- Do not add per-agent incident counts; the export does not support that join.

### Reliability Scorecard

Use cards with current value, comparison period, variance, and trend only when
the source supports them. NetPulse's documented 99% successful ingestion,
sub-second p95 processing, and under-60-second freshness goals are illustrative
portfolio/demo objectives, not production SLAs:

- `raw_event_age_seconds` can show current freshness against the illustrative
  60-second objective while traffic is active.
- The CSVs do not expose ingestion success or p95 processing latency, so do not
  build cards claiming those two objectives were measured.
- Probe success is not network availability and has no project-defined SLA.

Label objectives as “Portfolio/demo objective” everywhere they appear.

## Publish with Tableau Public

Tableau Public workbooks and their published data are publicly accessible.
Anyone may be able to download or inspect the underlying data.

1. Run the deterministic NetPulse demo and refresh analytics with
   `analytics-all`.
2. Run `tableau-export` and inspect all four CSV files locally.
3. Open the free Tableau Public application.
4. Connect to the generated CSV files in `tableau_exports/`.
5. Establish only the valid relationships described above.
6. Create the calculated fields, worksheets, and four dashboard views.
7. Publish the workbook to Tableau Public after a final privacy review.
8. Replace the README workbook placeholder with the public workbook URL.

Before step 7, confirm that the files contain no private IP addresses, source
agent identifiers, endpoint or target identifiers, SSIDs, BSSIDs, display names,
credentials, secrets, environment values, or personally identifying information.
Prefer simulator data. Pseudonymous agent keys reduce casual identification but
do not make arbitrary real-world source data anonymous.

## Limitations

- The selected curated views do not expose p95 latency.
- Incident-to-agent attribution and classifier evidence are not exported.
- Agent performance provides the latest observation date, not an exact latest
  observation timestamp.
- Pipeline health is one export-time snapshot, not retained history.
- The repository does not include a Tableau workbook file and does not automate
  Tableau Public publication or store Tableau credentials.
