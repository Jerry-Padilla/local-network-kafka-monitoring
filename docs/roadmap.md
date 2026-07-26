# Roadmap

1. Completed: validate the Phase 1 Compose acceptance suite and close local
   environment defects.
2. Software complete: the Raspberry Pi agent and bounded SQLite outbox pass
   Python 3.12 and local recovery acceptance. Physical Pi Zero W/Pi 3
   installation and resource validation remain.
3. Completed: Spark Structured Streaming parsing, watermarking, windowed
   metrics, checkpoints, curated PostgreSQL output, invalid evidence, and
   progress metrics pass local acceptance.
4. Next: add deterministic cross-agent incident rules, evidence, confidence, and the
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
