# Phase 5A analytics

The optional analytics job builds reproducible PostgreSQL reporting facts from
the operational tables. It is a one-shot batch job, not a continuously updated
dashboard. Run it after migrations and ingestion:

```powershell
./scripts/netpulse.ps1 analytics-build
./scripts/netpulse.ps1 analytics-all
./scripts/netpulse.ps1 analytics-verify
```

On POSIX systems, the equivalent commands are `make analytics-build`,
`make analytics-all`, and `make analytics-verify`. For an inclusive historical
UTC date range, run:

```bash
docker compose --profile analytics run --rm analytics \
  --from-date 2026-03-08 --through-date 2026-03-09
```

The job uses `network_measurements` and `service_checks` as its exact count
sources. Their `event_id` primary keys are the deduplication boundary. Spark
window metrics are not used for exact reconciliation. Dates come from
`event_time` in UTC. A selected date is fully replaced, including when source
rows have since been removed. Late arrivals require an explicit rerun of their
historical date or `analytics-all`; no automatic backfill is promised.

The daily fact grain is UTC date, agent, endpoint, source kind, and probe type.
`network_measurement` latency is `latency_ms`; `service_check` latency is
`total_duration_ms`. A NULL latency sum/mean means no latency was measured,
not zero milliseconds. Packet loss applies to network measurements. The
`v_daily_probe_reliability` view exposes observation counts, success rate,
and applicable means. It excludes speed tests and heartbeats. Probe success
rate is not a network availability SLA.

Agent and endpoint dimensions update their display attributes in place
(Type 1). `fact_incident` holds the current lifecycle revision for each
incident. Separate agent and endpoint bridges list affected entities; joining
both bridges directly can multiply rows. Use `v_incident_summary` for one row
per incident with independent affected-agent and affected-endpoint counts.

One PostgreSQL transaction refreshes the selected daily facts, the current
incident snapshot, and the successful job-run record. A failure rolls back
the whole refresh. `analytics-verify` runs `--all` and checks every current
source/fact grain and incident count; it exits nonzero on a mismatch.

## Read-only reporting login

The migration creates the `netpulse_report` NOLOGIN group role with SELECT
permission on the two reporting views. For a local Power BI login, open the
admin `psql` shell (`make db-shell` or `./scripts/netpulse.ps1 db-shell`) and
run:

```sql
CREATE ROLE netpulse_report_reader LOGIN;
GRANT netpulse_report TO netpulse_report_reader;
\password netpulse_report_reader
```

Choose the password interactively and store it only in your local reporting
client. Query `v_daily_probe_reliability` and `v_incident_summary`. The role
has no base-table grants. On an existing PostgreSQL volume, run the migration
first and create this login manually; no volume reset is needed. Revoke/drop
the login before a migration downgrade if role dependencies require it.

The default Compose PostgreSQL port is bound to loopback. Remote reporting
access and a public database listener are outside this local setup.
