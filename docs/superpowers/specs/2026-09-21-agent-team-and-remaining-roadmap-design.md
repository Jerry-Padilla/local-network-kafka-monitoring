# NetPulse agent team and remaining roadmap — design

## Purpose and current baseline

Use a small, reusable team of **Codex development agents** to finish NetPulse
without confusing them with the network-monitoring agents that emit telemetry.
The repository currently records Phases 1, 3, and 4 as locally accepted. Phase 2
software has local acceptance, but has not been exercised on the user's physical
Raspberry Pi 3 Model B+. Phase 5 onward remains unimplemented. Existing local
acceptance is not evidence of production scale or hardware compatibility.

The user has one Pi 3 B+ available, but it is not on hand or configured yet.
Hardware work must not block software-only Phase 5 planning or implementation.
No Pi address, network name, password, or broker credential belongs in chat or
the repository; use local configuration and secret storage when hardware is ready.

## Team design

The main Codex conversation is the **lead**: it owns architecture decisions,
sequencing, integration, user-facing status, and final verification. It delegates
bounded work only when independent work exists. Three project-scoped helper
roles live in `.codex/agents/` after this design is approved:

| Role | Primary ownership | Preferred model / effort | Boundary |
| --- | --- | --- | --- |
| Data engineer | Phase 5 warehouse model, rerunnable ETL, SQL views; later API data contracts | `gpt-5.6-sol` / medium | Does not change Pi deployment or approve its own work |
| Platform and Pi engineer | Pi 3 B+ compatibility, network-safe deployment, Compose/Kind/Kustomize, observability wiring | `gpt-5.6-terra` / medium | Does not invent device evidence or open a LAN listener without review |
| Independent verifier | Read-only review of migrations, tests, replay/failure behavior, security, and documentation claims | `gpt-5.6-terra` / high | Does not modify files or mark a phase complete |

The lead may use a stronger model for a difficult cross-component decision. A
fourth, always-on helper is not needed; narrow documentation research can be
handled on demand. Limit concurrent helpers to three, and use fewer when tasks
share files or depend on a predecessor. These model names are preferences for
the current Codex environment, not a guarantee of future model availability.

Each task brief names its deliverable, owned paths, dependencies, acceptance
commands, and prohibitions. Implementers report changed files and exact test
output. The verifier evaluates those files and claims independently; the lead
resolves findings and runs final checks. Helpers do not commit, push, deploy,
or alter Pi/firewall settings unless the user specifically authorizes that
operation. The verifier uses a read-only sandbox.

## Remaining delivery sequence and gates

1. **Pi 3 B+ hardware gate, in parallel with software work.** When the device
   is available, confirm the OS/Python version and interface names, validate the
   existing agent configuration offline, then prove SQLite queueing and Kafka
   delivery over an explicitly secured private-LAN path. Record CPU, memory,
   storage, and recovery observations. Keep secrets out of Git. One real Wi-Fi
   Pi plus a simulated Ethernet agent does not prove physical cross-agent
   diagnosis. If Python 3.12 is unavailable on the chosen OS, investigate and
   test a supported path before changing the install guide.
2. **Phase 5A — analytics model.** Design dimensions and incident/reliability
   facts with stable keys, event-time semantics, and explicit grain. Build
   idempotent, rerunnable batch jobs and versioned migrations. Publish
   Power BI-compatible read-only views. Acceptance covers replay, late data,
   duplicate IDs, empty inputs, and reconciliation to operational tables.
3. **Phase 5B — observability.** Expose bounded service metrics, provision
   Prometheus and Grafana locally, and test that dashboards reflect broker,
   consumer, outbox, Spark, and classifier health where measured. Do not label
   unmeasured infrastructure signals as implemented. This is a separate slice
   from the warehouse so either can be reviewed and accepted independently.
4. **Phase 6 — query API.** Add a read-only FastAPI service over stable analytics
   views. Define pagination, time filters, UTC serialization, input limits,
   error behavior, and a privacy boundary. Test contracts and query plans; do
   not expose raw credentials or unrestricted SQL.
5. **Phase 7 — local orchestration demonstration.** Package the accepted
   services for Kind/Kustomize with health probes, bounded resources, secrets
   supplied outside Git, migrations, and reproducible smoke tests. Keep this a
   local demonstration, not a production-Kubernetes claim.
6. **Phase 8 — measured experiments.** Run reproducible throughput, outage,
   replay, recovery-time, and Pi-resource experiments only after the relevant
   stack is deployable. Record methodology, environment, exact commands,
   outputs, limitations, and capacity conclusions without extrapolation.
7. **Phase 9 — optional extensions.** Consider local citation-bearing RAG and a
   bounded read-only MCP server only if the core stack has met its acceptance
   gates and the user wants those extensions. They are not prerequisites for
   the monitoring project.

For each slice, the lead requires implementation, focused and regression tests,
security/privacy review, reproducible startup or invocation, and docs aligned
with observed behavior. A phase stays unverified when hardware or container
acceptance cannot run. The verifier's findings are a review input, not a
substitute for the lead's checks.

## First handoff after approval

Create the three project-scoped TOML agent definitions and a small project
agent concurrency setting. Add a short operating guide with task-brief and
review templates. Then write an implementation plan for Phase 5A only; Phase
5B and later phases receive their own specs/plans when reached. The physical
Pi gate gets a separate checklist after the user has the device in hand.

## Explicit non-goals

This design does not install software on the Pi, create a second physical
agent, add new telemetry collectors, open network ports, implement analytics
or the API, deploy Kubernetes, or claim measured performance. It also does not
start all helper agents continuously: delegation is per bounded task.
