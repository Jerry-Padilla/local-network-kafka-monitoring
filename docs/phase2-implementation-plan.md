# Phase 2 implementation checklist

- [x] Preserve Phase 1 in a local Git checkpoint.
- [x] Add YAML configuration and explicit environment overrides.
- [x] Add router/external ping, DNS, HTTP, Wi-Fi, heartbeat, and optional
  speed-test collectors.
- [x] Add privacy controls for endpoint addresses, SSIDs, and BSSIDs.
- [x] Add a bounded durable SQLite outbox with retained acknowledgements.
- [x] Add Kafka callback-gated delivery and bounded retry scheduling.
- [x] Isolate collectors and publication so backend outages do not stop
  collection.
- [x] Add an opt-in development image and cross-platform workflows.
- [x] Add systemd assets and Raspberry Pi installation guidance.
- [x] Add mock-based unit and contract tests.
- [x] Execute Python 3.12 container tests and live Kafka recovery acceptance.
- [ ] Validate installation and resource use on the target Pi 3 B+ running
  64-bit Raspberry Pi OS Lite Trixie. Pi Zero models are out of scope.

Phase 3 must not begin until the software acceptance suite passes. Physical Pi
validation can remain an explicitly recorded hardware limitation, but must not
be claimed as completed.
