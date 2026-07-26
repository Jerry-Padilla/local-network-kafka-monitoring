# NetPulse repository guidance

## Repository overview

NetPulse is a portfolio-oriented, multi-agent home-network observability
prototype. Phase 1 implements a local at-least-once ingestion path from a
deterministic simulator through Kafka to PostgreSQL. Later phases add the
Raspberry Pi agent, Spark, incident classification, analytics, dashboards,
API, and Kubernetes.

## Service map

- `packages/contracts`: common event models, topic routing, and validation.
- `services/simulator`: deterministic two-agent Kafka producer.
- `services/event-ingestor`: validation, dead-letter routing, deduplication,
  and PostgreSQL persistence.
- `database`: Alembic migrations and database tests.
- `schemas`: versioned JSON Schema contracts.
- `scripts`: cross-platform developer and stack-verification commands.

## Engineering rules

1. Inspect relevant files before modifying them and preserve useful behavior.
2. Use Python 3.12, type hints, UTC-aware timestamps, structured logging,
   bounded retries, and explicit configuration.
3. Validate events before publication and after consumption.
4. Never commit Kafka offsets before durable handling and required publication
   acknowledgements complete.
5. Preserve at-least-once semantics and deduplicate by `event_id`; never claim
   end-to-end exactly-once delivery.
6. Do not swallow exceptions, commit credentials, interpolate untrusted shell
   input, or monitor endpoints that were not explicitly configured.
7. Treat anomalous but structurally valid telemetry as valid data.
8. Add meaningful tests and update documentation with every behavior change.
9. Run targeted checks after material changes and the full feasible suite
   before completion.
10. Never fabricate test, benchmark, scale, availability, or recovery claims.

## Commands

- `make lint` / `./scripts/netpulse.ps1 lint`
- `make typecheck` / `./scripts/netpulse.ps1 typecheck`
- `make test` / `./scripts/netpulse.ps1 test`
- `make test-integration` / `./scripts/netpulse.ps1 test-integration`
- `make up`, `make demo`, `make verify`, `make down`
- Windows equivalents use `./scripts/netpulse.ps1 <command>`.

## Definition of done

A change is complete only when implementation, configuration, meaningful tests,
error handling, security considerations, and accurate documentation are
present. Report exact commands and outcomes, skipped checks, environmental
limitations, and remaining work. Keep the repository runnable after every
phase.
