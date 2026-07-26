# Phase 3 completion report

## Completed

Spark Structured Streaming 4.1.2 now reads raw Kafka measurements, validates
the projected version 1 contract, applies a 15-minute event-time watermark,
maintains four window sizes, persists curated metrics with replay-safe keys,
and stores invalid source evidence separately. PostgreSQL reached Alembic
revision `0003`.

The service runs as non-root on Python 3.12.10 and Java 17. The upstream Spark
Docker image was not used because its inspected `4.1.2-python3` tag contained
Python 3.10.12.

## Validation performed

Observed on 2026-07-26:

- Compose configuration passed on Docker 29.6.2.
- The stream-processor and updated Python 3.12 test images built.
- Ruff passed and strict MyPy passed across 45 source files.
- Targeted Phase 3/migration suite: 16 passed.
- Full unit/contract suite: 92 passed and 2 integration tests deselected.
- Docker-backed regression integration suite: 2 passed and 92 deselected.
- Branch coverage: 82.25%, above the required 80%.
- Offline Alembic SQL generation passed through revisions 0001, 0002, and 0003.
- Alembic live revision: `0003`.
- Initial `available-now` run read the existing three-partition raw topic and
  wrote 234 unique curated aggregate rows.
- All window sizes were present: 60, 300, 900, and 86,400 seconds.
- Both fabricated agents were present.
- Spark stored 11 source-coordinate processing failures.
- Aggregate duplicate-key count was zero.
- A second deterministic batch resumed from the same checkpoint, advanced
  stored batch IDs, produced 244 total aggregate rows, retained 11 rejects,
  and still reported zero duplicate keys.
- The Kafka connector resolved once from Maven Central and the second run
  reused all 11 cached artifacts.
- Compose, Linux shell syntax, PowerShell parser validation, and the non-root
  `netpulse` stream image user passed inspection.

The initial Spark attempt failed before consuming offsets because the new Ivy
volume was not writable by the non-root UID. The image was corrected to
pre-create and own the cache directories; only the disposable Ivy cache volume
was recreated. The untouched checkpoint then completed successfully.

## Remaining limitations

- GitHub-hosted Actions results have not been inspected because GitHub CLI is
  not authenticated; equivalent workflows were executed locally.
- Physical Pi Zero W/Pi 3 validation remains open.
- Service-check, speed-test, and heartbeat streaming aggregates are not
  implemented.
- Deterministic incident classification starts in Phase 4.
- This is a single-machine `local[2]` Spark deployment, not a distributed
  performance or capacity claim.
- Percentiles are approximate and no throughput benchmark is claimed.

## Next highest-value task

Implement Phase 4 deterministic cross-agent incident correlation over the
curated event-time windows, including confidence, evidence, lifecycle state,
Kafka output, PostgreSQL persistence, and scenario acceptance tests.
