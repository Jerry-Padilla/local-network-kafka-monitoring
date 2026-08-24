# Phase 4 implementation checklist

- [x] Add a truthful `system_classifier` producer role to the version 1 envelope.
- [x] Add configurable, deterministic multi-agent correlation rules.
- [x] Suppress single-sample failures.
- [x] Add confidence, evidence, severity, affected scope, and diagnostic action.
- [x] Add candidate, open, ongoing, recovering, and resolved transitions.
- [x] Add replay-safe PostgreSQL lifecycle storage.
- [x] Add an acknowledgement-gated PostgreSQL-to-Kafka incident outbox.
- [x] Add a non-root classifier image and opt-in Compose profile.
- [x] Add matching Make, POSIX, PowerShell, verification, and CI commands.
- [x] Add rule, lifecycle, configuration, contract, and migration tests.
- [x] Execute the Docker-backed scenario and lifecycle verification.
- [x] Record the complete feasible acceptance output.

Phase 5 warehouse and dashboard work must not begin until the feasible Phase 4
acceptance suite passes. Physical Raspberry Pi validation remains an independent
Phase 2 hardware gate.
