# Roadmap

1. Completed: validate the Phase 1 Compose acceptance suite and close local
   environment defects.
2. Software complete: the Raspberry Pi agent and bounded SQLite outbox pass
   Python 3.12 and local recovery acceptance. The agent and contracts packages
   also permit Python 3.13, with a separate x86_64 CI check. Physical Pi 3 B+
   installation and resource validation remain; Pi Zero models are out of scope.
3. Completed: Spark Structured Streaming parsing, watermarking, windowed
   metrics, checkpoints, curated PostgreSQL output, invalid evidence, and
   progress metrics pass local acceptance.
4. Completed: deterministic cross-agent incident rules, evidence, confidence,
   durable Kafka publication, and the
   candidate-to-resolved state machine.
5. Software complete: dimensional reporting, Prometheus, Alertmanager,
   provisioned Grafana dashboards, read-only monitoring identities, and
   reversible failure-drill tooling. Physical Pi acceptance remains the gate.
6. Completed: the loopback-only, read-only FastAPI daily reliability query
   layer passes live HTTP, privilege, index-plan, and operator checks.
7. Demonstrate orchestration with Kind and Kustomize.
8. Run physical Pi acceptance and measured performance/failure experiments;
   write capacity conclusions only from captured evidence.
9. Consider local, citation-bearing RAG and a bounded read-only MCP server only
   after all core acceptance criteria pass.

Each phase is gated by implementation, tests, reproducible startup, security
considerations, and documentation matching observed behavior.
