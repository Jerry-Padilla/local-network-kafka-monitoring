# Known limitations

- Phase 1 acceptance has been demonstrated on the local Windows/Docker Desktop
  environment recorded in the completion report. This is not a production,
  multi-host, or hardware-agent validation.
- One Kafka broker and one PostgreSQL instance provide no high availability.
- Kafka uses plaintext local listeners and development credentials.
- Kafka and PostgreSQL persistent state must be backed up, restored, or reset
  together. If Kafka offsets rewind while PostgreSQL is retained, replay-safe
  source-coordinate deduplication can classify new low offsets as historical
  duplicates until the broker advances beyond the stored offsets.
- There is no atomic Kafka/PostgreSQL transaction; output records can repeat.
- The simulator is evidence-generating test software, not real network
  measurement hardware, and has no durable local queue.
- The Phase 2 agent has mocked tests and local Docker/Kafka recovery evidence,
  but has not yet been installed or resource-tested on the target Pi 3 B+.
  Pi Zero models are outside the current hardware scope.
- The default backend Kafka listener is loopback-only. A Pi requires an
  explicitly secured private-LAN listener; this is not enabled automatically.
- Spark runs as a local two-thread driver and is not a distributed scale claim.
  Its approximate percentiles use accuracy 10,000, and its bounded driver sink
  is intended for aggregate rather than raw-event cardinality.
- The Phase 3 job currently aggregates network measurements only. Service
  checks, speed tests, and heartbeats remain in operational tables.
- Prometheus, Alertmanager, exporters, and Grafana run on one Docker host and
  therefore do not provide an independent monitoring failure domain.
- The container-resources dashboard measures Linux-container working sets from
  cAdvisor. It does not account for all Docker Desktop VM cache, daemon, or host
  memory and therefore cannot equal Task Manager's total Docker/WSL footprint.
- Incident classification uses static deterministic thresholds over a bounded
  database snapshot. It has no learned baseline, seasonality model, or
  definitive access to router/ISP internals.
- PostgreSQL analytics, read-only SRE views, the loopback-only query API, and
  optional Airflow orchestration are implemented. Grafana remains the supported
  operational dashboard. Tableau support exports CSV datasets only; the
  repository does not contain or publish a Tableau workbook. Kubernetes, RAG,
  and MCP are outside the completed `master` scope.
- No throughput, recovery-time, or capacity figures are claimed.
