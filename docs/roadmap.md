# Roadmap

1. Validate the complete Phase 1 Compose acceptance suite and close any
   environment-specific defects.
2. Build the lightweight Raspberry Pi agent with configurable ping, DNS, HTTP,
   Wi-Fi, heartbeat, optional speed-test collectors, and a bounded SQLite
   outbox.
3. Add Spark Structured Streaming parsing, watermarking, windowed metrics,
   checkpoints, curated PostgreSQL output, and progress metrics.
4. Add deterministic cross-agent incident rules, evidence, confidence, and the
   candidate-to-resolved state machine.
5. Add dimensional facts/dimensions, rerunnable batch jobs, Power BI views,
   Prometheus, and provisioned Grafana dashboards.
6. Add the read-only FastAPI query layer.
7. Demonstrate orchestration with Kind and Kustomize.
8. Run measured performance/failure experiments and write capacity conclusions.
9. Consider local, citation-bearing RAG and a bounded read-only MCP server only
   after all core acceptance criteria pass.

Each phase is gated by implementation, tests, reproducible startup, security
considerations, and documentation matching observed behavior.
