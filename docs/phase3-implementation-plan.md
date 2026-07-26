# Phase 3 implementation checklist

- [x] Pin Spark, Java, Python, Kafka connector, and PostgreSQL dependencies.
- [x] Add typed raw-measurement parsing with additive-field compatibility.
- [x] Add malformed and invalid record evidence keyed by Kafka coordinates.
- [x] Add a configurable event-time watermark.
- [x] Add 1-minute, 5-minute, 15-minute, and daily aggregates.
- [x] Add count, reliability, latency, jitter, packet-loss, and freshness metrics.
- [x] Add bounded replay-safe PostgreSQL `foreachBatch` sinks.
- [x] Add persistent Spark state/checkpoint and Ivy cache volumes.
- [x] Add structured streaming progress logs.
- [x] Add deterministic Spark transformation and migration tests.
- [x] Demonstrate an initial run and restart from the same checkpoint.
- [x] Add cross-platform build, run, one-shot, and verification commands.
- [x] Add a separate GitHub Actions streaming integration job.

Phase 4 incident classification is intentionally not part of this checklist.
Physical Raspberry Pi validation remains an independent Phase 2 hardware gate.
