# Phase 2 software completion report

## Outcome

The Raspberry Pi network-agent software passed its complete feasible local
acceptance suite on 2026-07-26 UTC. It now provides:

- YAML configuration with explicit environment overrides;
- router and external ping, DNS, bounded HTTP, Wi-Fi, heartbeat, and optional
  non-overlapping speed-test collectors;
- default omission or configurable hashing of SSID/BSSID values;
- default omission of raw endpoint addresses;
- a size-bounded SQLite WAL outbox with full synchronization;
- persisted sequence numbers, original event timestamps, retry count, last
  error, bounded exponential backoff, jitter, and acknowledged-row retention;
- Kafka callback-gated delivery on an independent worker;
- per-collector scheduling so a backend outage does not block collection;
- a non-root development image and hardened systemd service assets.

Phase 1 was preserved first in local commit `6798e4d`. Phase 3 was not started.

## Automated validation

| Check | Observed result |
|---|---|
| `ruff format --check .` | 72 files already formatted |
| `ruff check --no-cache .` | All checks passed |
| `mypy` | No issues in 39 source files |
| Python 3.12 unit/contract suite | 79 passed, 2 deselected |
| Python 3.12 coverage | 85.46%; required 80% reached |
| Docker integration suite | 2 passed, 79 deselected |
| Focused agent suite | 25 passed |
| Compose configuration | Passed |
| Agent and test image builds | Passed |
| Alembic offline SQL generation | Revisions 0001 and 0002 passed |
| Live migration | Database reached revision 0002 |
| PowerShell parser | Passed |
| Linux shell syntax | Passed in the Kafka image |

The agent integration test first targeted an unavailable Kafka address. The
event remained pending with retry metadata and no acknowledgement. The same
SQLite event was then delivered to the real Kafka broker and persisted by the
Phase 1 ingestor with its original `event_time`.

## Live collection and outbox evidence

A real network-agent container ran all six enabled sample collectors with Kafka
publication disabled:

```text
enqueued=7
acknowledged=0
failed=0
outbox_depth=7
```

The next publication invocation reported seven acknowledgements and zero
pending rows. A second round after switching ingestion reference validation to
the PostgreSQL catalog also delivered all seven records without adding a dead
letter.

The agent then ran headlessly for 15 seconds and stopped through SIGTERM:

```text
agent_started collectors=6
acknowledged delivery batches: 3, 2, 2, 1, 1
agent_stopped outbox_depth=0
```

Its persistent outbox ended with 23 acknowledged rows retained and zero
pending. The final database snapshot reported:

```text
network.agent_heartbeat=3
network.measurement=15
network.service_check=6
source_version 0.2.0 events=24
alembic revision=0002
```

The final processing-failure count was eight. The newest failure was the
intentional malformed Phase 1 integration fixture; the final headless agent run
added no dead letters. Kafka, PostgreSQL, and the ingestor were healthy.

## Remaining hardware gate

No physical Raspberry Pi was available. Therefore the following are not
claimed:

- installation success on Pi Zero W or Pi 3;
- ARM wheel/source-build compatibility for `confluent-kafka`;
- measured CPU, memory, temperature, disk growth, or power use;
- real `iw` output for the user's adapter/driver;
- real service behavior across Wi-Fi and power interruptions.

The development image was built and inspected as non-root user `netpulse` on
amd64. Raspberry Pi deployment intentionally uses the Python package and
systemd instructions, not that amd64 image. Phase 2 hardware acceptance remains
open until `docs/raspberry-pi-setup.md` is executed on both target devices.
