# Phase 5B — self-hosted SRE observability design

## Intent and boundary

Turn NetPulse into a credible, zero-software-cost data-engineering and SRE
portfolio system. The Raspberry Pi 3 Model B+ is the required deployed edge
collector. The deterministic simulator remains the repeatable acceptance-data
source, and the Docker network agent remains an integration fixture for the
same collector, SQLite outbox, and Kafka recovery code used on the Pi.

This phase adds metrics, dashboards, alerting, runbooks, and measured failure
drills. It does not add Snowflake, Power BI, Loki, distributed tracing,
Kubernetes, FastAPI, RAG, or MCP functionality.

## Target architecture

The data plane remains unchanged: the Pi durably queues measurements in its
SQLite outbox, publishes them to the private-LAN Kafka listener, and the event
ingestor validates and deduplicates them into PostgreSQL. Spark builds
event-time aggregates, the classifier maintains incident lifecycle state, and
the existing analytics job refreshes PostgreSQL facts, dimensions, and
reporting views.

The observability plane uses self-hosted Prometheus, Alertmanager, and Grafana
OSS. Prometheus scrapes bounded application metrics plus Kafka and PostgreSQL
exporters. Grafana reads operational metrics from Prometheus and network
reliability/incident views from PostgreSQL through a dedicated read-only role.
Alertmanager groups and exposes alerts locally; external notification services
are not required.

## Component roles

- The Raspberry Pi is mandatory. It is the initial wired reference observer
  and runs router ping, external ping, DNS, and heartbeat collectors. Wi-Fi,
  HTTP, and speed-test collectors remain disabled for initial deployment.
- The Pi writes every event to the existing bounded SQLite outbox before Kafka
  publication and retains pending events across Kafka outages and reboots.
- The simulator supplies deterministic healthy, failure, malformed, duplicate,
  and recovery scenarios for CI and portfolio demonstrations.
- The Docker agent validates collector scheduling, durable queuing, publication,
  and recovery without replacing physical Pi acceptance. Its Docker-safe
  configuration uses a container-observer identity, disables Wi-Fi and speed
  testing, and uses explicitly configured reachable targets rather than
  documentation-only addresses.
- PostgreSQL remains both the operational system of record and the analytical
  warehouse. Grafana replaces Power BI as the supported visualization layer.

## Metrics contract

Long-running NetPulse services expose `GET /metrics` on a configurable internal
address and port using the Prometheus text format. Metrics use the
`netpulse_` prefix and bounded labels only. Event IDs, target addresses,
exception messages, SSIDs, BSSIDs, and arbitrary user-supplied values must
never appear in metric labels.

The ingestor exposes consumed outcomes, validation/deduplication results,
processing duration, downstream publication acknowledgements/failures, retry
activity, and last successful durable processing time. The stream processor
exposes batch outcomes, accepted/rejected rows, batch duration, and last
successful batch time. The classifier exposes evaluation outcomes, incident
state transitions, publication outcomes, pending outbox count, and last
successful evaluation time. The agent exposes collector outcomes, publication
outcomes, current outbox depth, oldest pending-record age, and last successful
collection/publication times.

Kafka exporter supplies broker/topic/consumer-group metrics, including lag.
PostgreSQL exporter supplies database availability, connections, transactions,
locks, and storage activity. Exporters receive least-privilege credentials.

Metrics endpoints are internal to Compose by default. The Pi endpoint is
reachable only on the private LAN and is never exposed to the public internet.

## Dashboards and objectives

Grafana is provisioned from repository-controlled files with no manual setup.
It provides three dashboards:

1. Platform health: scrape state, service health, Kafka health, PostgreSQL
   health, and dependency failures.
2. Pipeline reliability: throughput, consumer lag, success/error ratios,
   processing latency, dead-letter growth, publication failures, freshness,
   and queue backlog.
3. Network reliability: probe success, latency, packet loss, agent freshness,
   current incidents, and incident lifecycle from read-only PostgreSQL views.

The repository documents illustrative portfolio objectives rather than
production claims: 99% successful ingestion while traffic is expected, p95
ingestion processing latency below one second, durable data freshness within
60 seconds during an active scenario, and no sustained unpublished incident
outbox records. Recording rules calculate the corresponding ratios, latency,
freshness, and error-budget consumption while safely handling zero traffic.

## Alerts and runbooks

Alert rules cover scrape target loss, PostgreSQL unavailability, Kafka consumer
lag, stale ingestion while traffic is expected, dead-letter growth, sustained
processing failures, classifier stalls, incident publication backlog, Pi
freshness loss, and Pi outbox backlog. Every alert includes severity, impact,
likely causes, and a repository runbook link. Disabled optional profiles do not
produce false alerts.

Alertmanager groups related alerts and provides local silence and inspection
interfaces. Local UI/API evidence is sufficient for this phase; email, Slack,
PagerDuty, and other hosted receivers remain optional future integrations.

## Deployment and security

The monitoring stack is an opt-in Docker Compose `monitoring` profile. Grafana,
Prometheus, and Alertmanager host ports bind to `127.0.0.1`. Their data uses
named volumes. Images use explicit version tags and are never pulled through a
floating `latest` tag.

Grafana receives one PostgreSQL login that inherits only the existing reporting
view permissions. PostgreSQL exporter uses a separate monitoring login with the
minimum built-in monitoring grants. Passwords live only in the local `.env`;
the repository contains variable names and non-secret examples.

The private-LAN Kafka listener remains scoped to the Windows Private firewall
profile and the local subnet. The monitoring work must not broaden Kafka,
PostgreSQL, Grafana, Prometheus, Alertmanager, or Pi metrics exposure.

## Verification and acceptance

Tests must prove metric counters and gauges reflect success, failure, retry,
queue, and recovery behavior; metric labels remain bounded and privacy-safe;
and metrics servers start and stop cleanly. Prometheus and Alertmanager
configuration must pass their native validation tools. Provisioned Grafana
datasources and dashboards must load without manual edits.

An end-to-end demonstration starts the core, simulator, streaming,
classification, analytics, and monitoring profiles; generates deterministic
traffic; and verifies nonempty PostgreSQL data, Prometheus targets, Grafana
datasources, and normal alert state. Failure drills then stop Kafka, stop
PostgreSQL, publish malformed traffic, and pause traffic. Each drill records
alert detection, recovery, and the existing replay/deduplication invariants.

Physical Pi acceptance remains mandatory. It verifies first-boot provisioning,
systemd enablement, real collection, pending SQLite records with Kafka stopped,
reboot persistence, backlog publication after Kafka returns, PostgreSQL
ingestion, Prometheus Pi visibility, Grafana freshness/outbox panels, and alert
firing plus resolution when the Pi becomes unavailable and returns.

The development baseline uses Python 3.12 for the complete repository. The
full declared development dependencies, including PySpark, must be installed
before local unit results are considered complete. Exact commands, versions,
test outcomes, drill timestamps, and unavailable physical checks are recorded;
the project makes no unmeasured availability or recovery-time claims.
