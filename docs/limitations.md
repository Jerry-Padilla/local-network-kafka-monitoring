# Known limitations

- Phase 1 acceptance has been demonstrated on the local Windows/Docker Desktop
  environment recorded in the completion report. This is not a production,
  multi-host, or hardware-agent validation.
- One Kafka broker and one PostgreSQL instance provide no high availability.
- Kafka uses plaintext local listeners and development credentials.
- There is no atomic Kafka/PostgreSQL transaction; output records can repeat.
- The simulator is evidence-generating test software, not real network
  measurement hardware, and has no durable local queue.
- The Phase 2 agent has mocked tests and local Docker/Kafka recovery evidence,
  but has not yet been installed or resource-tested on a physical Pi Zero W or
  Pi 3.
- The default backend Kafka listener is loopback-only. A Pi requires an
  explicitly secured private-LAN listener; this is not enabled automatically.
- Spark runs as a local two-thread driver and is not a distributed scale claim.
  Its approximate percentiles use accuracy 10,000, and its bounded driver sink
  is intended for aggregate rather than raw-event cardinality.
- The Phase 3 job currently aggregates network measurements only. Service
  checks, speed tests, and heartbeats remain in operational tables.
- Kafka consumer-lag, infrastructure metrics, Grafana, and alerting are later
  phases.
- Incident classification uses static deterministic thresholds over a bounded
  database snapshot. It has no learned baseline, seasonality model, or
  definitive access to router/ISP internals.
- No warehouse, Power BI views, API, Kubernetes, RAG, or MCP layer exists.
- No throughput, recovery-time, or capacity figures are claimed.
