# Phase 4 completion report

## Completed

NetPulse now has a deterministic multi-agent incident classifier covering all
ten contract classes. It correlates typed network measurements, service checks,
and heartbeat freshness over a bounded event-time snapshot. Findings include
probable-cause language, confidence, evidence, severity, affected scope, and a
fixed diagnostic action.

The lifecycle requires two positive observations to open and two healthy
observations to resolve. PostgreSQL revision `0004` stores current/historical
state and a serialized outbox. Kafka acknowledgement is required before an
outbox row is marked published; replay uses a stable event ID.

## Validation performed

Observed on 2026-07-26 with Docker 29.6.2:

- Compose configuration passed.
- The Python 3.12 test and non-root classifier images built.
- Ruff formatting and linting passed across the repository.
- Strict MyPy passed across 54 source files.
- Full unit/contract suite: 130 passed and 2 integration tests deselected.
- Branch coverage: 82.17%, above the required 80%.
- Focused classifier suite after the final unknown-incident rule: 36 passed.
- All nine seeded failure scenarios with explicit expected classifications
  produced the expected rule result.
- Offline Alembic SQL generation passed through revisions 0001–0004.
- Live Alembic revision was `0004`.
- Docker-backed ingestion/outbox regression suite: 2 passed and 128 deselected.
- Seeded Wi-Fi degradation produced `candidate` then `open`; healthy traffic
  produced `recovering` then `resolved`.
- `scripts/verify_classification.py` printed
  `Phase 4 classification invariants passed`.
- The live outbox contained zero pending rows.
- A `network.incidents.v1` console read returned the evidence-bearing
  `wifi_degradation` candidate with `system_classifier` role.
- Image inspection reported the classifier user as `netpulse`.

The first lifecycle workflow used a 5-second window while Compose re-ran
one-shot dependency jobs. The evidence expired before evaluation, so no finding
was produced. Adding `--no-deps` reused the healthy stack. A second run showed
the positive window also needed to span both one-shot process startups; the
verification now uses 15 seconds for opening and 5 seconds after six seconds of
healthy traffic for recovery. The corrected workflow then passed.

## Remaining limitations

- Physical Pi Zero W/Pi 3 installation and resource validation remain open.
- Rules use static thresholds and do not learn per-agent baselines or
  seasonality.
- The classifier observes symptoms in validated data and cannot confirm router,
  ISP, resolver, or remote-service internals.
- The service is a single polling process; multi-replica leader election and
  performance/capacity behavior have not been demonstrated.
- PostgreSQL and Kafka are not atomic. A lost acknowledgement can republish the
  same stable incident event ID.
- GitHub-hosted workflow results were not inspected in this run.

## Next highest-value task

Implement Phase 5 dimensional incident/reliability facts, rerunnable batch ETL,
Power BI-compatible views, and provisioned Grafana dashboards. Keep physical Pi
validation as an independent hardware gate.
