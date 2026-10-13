# Project status

- **Last audited:** October 13, 2026
- **Checkout:** integrated `master` candidate
- **Release base:** `v1.0.0` / `origin/master` at `e64292f`

## Summary

This checkout contains the released NetPulse ingestion, Pi-agent, streaming,
incident-classification, analytics, query-API, and SRE-observability paths plus
optional Airflow orchestration and Tableau CSV export. It is a local portfolio
prototype, not a production service or a completed hardware deployment.

The local integration combines the previously separate Airflow and Tableau
branches. Kind/Kustomize work remains on a separate divergent branch and is not
present in this checkout.

## Verified in this audit

| Check | Command | Result |
|---|---|---|
| Compose rendering | `docker compose config --quiet` | Passed |
| Lint | `./scripts/netpulse.ps1 lint` | Passed |
| Strict typing | `./scripts/netpulse.ps1 typecheck` | Passed; 87 source files |
| Integrated non-integration suite | `./scripts/netpulse.ps1 test` | Passed; 488 tests, 13 deselected; 87.53% coverage |
| Live integration tests | `./scripts/netpulse.ps1 test-integration` | Passed; 6 tests, 448 deselected |
| Ingestion invariants | `./scripts/netpulse.ps1 verify` | Passed; 67 raw events, 31 typed measurements, 0 duplicate IDs |
| Spark streaming | `./scripts/netpulse.ps1 stream-verify` | Passed; 56 curated windows, 6 expected invalid records, 0 duplicate aggregate keys |
| Incident lifecycle | `./scripts/netpulse.ps1 classifier-verify` | Passed |
| Analytics reconciliation | `./scripts/netpulse.ps1 analytics-verify` | Passed; 18 daily grains, 2 incidents |
| Query API integration | `./scripts/netpulse.ps1 api-integration` | Passed; 6 tests |
| Query API smoke check | `./scripts/netpulse.ps1 api-verify` | Passed; health and cursor pagination |
| Observability plane | host HTTP/API and SQL checks | Passed; 7 targets, 0 required down, 2 healthy rule groups, 3 SRE agents |
| Tableau export | `./scripts/netpulse.ps1 tableau-export` | Passed; four promoted CSV files |

The audit also removed a host-only Git dependency from the Tableau deployment
test. The test now validates the repository's `.gitignore` entry directly, so
the documented containerized suite works from both a normal checkout and a
linked Windows worktree.

Live acceptance used an isolated Compose project with matched fresh Kafka and
PostgreSQL volumes. Grafana 13.2.2 was healthy on `127.0.0.1:3000`, and all
three provisioned NetPulse dashboards were returned by its API. The Windows
Tableau workflow now promotes exports with native PowerShell, so it no longer
depends on a separately installed host Python interpreter.

## Implemented in this checkout

- Versioned telemetry contracts, deterministic simulation, Kafka ingestion,
  dead-letter evidence, PostgreSQL persistence, and replay-safe deduplication.
- A configurable Raspberry Pi agent with privacy controls and a bounded,
  acknowledgement-gated SQLite outbox.
- Spark event-time curation, deterministic incident classification, and durable
  incident publication.
- Rerunnable daily analytics, read-only reporting views, a loopback-only query
  API, Prometheus, Alertmanager, Grafana dashboards, and operational runbooks.
- Optional Airflow LocalExecutor orchestration with source-quality gates,
  reconciliation, bounded retries/backfills, and persisted workflow status.
- Validated, privacy-reduced Tableau CSV exports with atomic promotion and a
  documented synthetic-data workbook workflow.

## Open acceptance gates

- Run the reversible failure drills and integrated live Airflow/Tableau
  acceptance together on the merged `master` branch.
- Install and exercise the agent on the target Raspberry Pi 3 B+, including
  outage recovery, reboot persistence, metrics, and dashboard visibility.
- Build, privacy-review, and publish the Tableau Public workbook; no public URL
  is currently claimed.
- Reconcile the remaining Kind/Kustomize branch before presenting it as part of
  the combined system.
- Capture evidence before making throughput, recovery-time, capacity, or
  production-readiness claims.

## Branch inventory

| Branch | Relative state | Capability | Integration status |
|---|---|---|---|
| `master` | Ahead of `origin/master` | Airflow orchestration plus Tableau CSV export and guide | Integrated locally |
| `codex/sre-observability` | Diverged from `v1.0.0` | Kind/Kustomize deployment and acceptance tooling | Separate local branch |

Branch state describes the local repository at audit time and may change as
work is pushed or rebased.
