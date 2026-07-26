# Known limitations

- Phase 1 acceptance has been demonstrated on the local Windows/Docker Desktop
  environment recorded in the completion report. This is not a production,
  multi-host, or hardware-agent validation.
- One Kafka broker and one PostgreSQL instance provide no high availability.
- Kafka uses plaintext local listeners and development credentials.
- There is no atomic Kafka/PostgreSQL transaction; output records can repeat.
- The simulator is evidence-generating test software, not real network
  measurement hardware, and has no durable local queue.
- Kafka consumer-lag, infrastructure metrics, Grafana, and alerting are later
  phases.
- Static anomaly scoring and incident classification are not implemented.
- No Spark, warehouse, Power BI views, API, Kubernetes, RAG, or MCP layer exists.
- No throughput, recovery-time, or capacity figures are claimed.
