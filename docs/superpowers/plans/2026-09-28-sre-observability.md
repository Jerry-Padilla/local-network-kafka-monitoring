# NetPulse SRE Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a zero-cost, self-hosted Prometheus, Alertmanager, and Grafana observability plane with mandatory Raspberry Pi monitoring, actionable alerts, runbooks, and measured failure drills.

**Architecture:** NetPulse services expose bounded Prometheus metrics through one shared Python package. A Compose `monitoring` profile runs Prometheus, Alertmanager, Grafana OSS, Kafka exporter, and PostgreSQL exporter; Grafana reads both Prometheus and read-only PostgreSQL reporting views. The Pi remains the required wired edge collector, while the simulator and Docker agent provide repeatable development and failure evidence.

**Tech Stack:** Python 3.12, prometheus-client 0.26.0, Docker Compose, Prometheus 3.14.0, Alertmanager 0.34.1, Grafana OSS 13.2.2, postgres_exporter 0.20.1, kafka_exporter 1.10.0, PostgreSQL 17, Kafka 4.2, Spark 4.1.2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-sre-observability-design.md`

## Global Constraints

- The Raspberry Pi 3 Model B+ is a required wired reference collector and physical acceptance is a release gate.
- Every core capability must run locally without a paid service or cloud account.
- PostgreSQL remains the operational store and analytics warehouse; Snowflake and Power BI are excluded.
- Grafana, Prometheus, and Alertmanager host ports bind only to `127.0.0.1`.
- Kafka's Pi-facing listener remains restricted to the Windows Private profile and local subnet.
- Metrics use the `netpulse_` prefix and bounded labels; never label by event ID, address, error text, SSID, BSSID, or arbitrary input.
- Existing at-least-once delivery, event-ID deduplication, SQLite outbox limits, privacy behavior, and PostgreSQL grants must remain intact.
- Optional Compose profiles must not create alerts when disabled.
- Image and Python dependency versions are pinned; no floating `latest` tags.
- Do not claim availability, latency, recovery, or Pi acceptance that was not measured.

## Review Focus

- A metrics bind failure must stop only the explicitly enabled service and must never silently run unmonitored; Task 1 tests invalid addresses and occupied ports.
- Replayed duplicate events must increment a bounded duplicate outcome without changing existing persistence/publication semantics; Task 2 tests duplicate insertion and output publication.
- Metrics collection must not block ingestion, Spark batches, classifier cycles, or Pi collection when Prometheus is unavailable; Tasks 2–4 test operation without a scraper.
- Disabled services and an unconfigured Pi scrape target must not fire false alerts; Tasks 6–7 validate target generation and alert expressions with empty series.
- Monitoring credentials must be read-only and idempotently provisionable on both fresh and existing PostgreSQL volumes; Task 5 tests reruns and denied writes.

---

### Task 1: Shared metrics package and reproducible Python baseline

**Files:**
- Create: `packages/observability/pyproject.toml`
- Create: `packages/observability/src/netpulse_observability/{__init__.py,http.py}`
- Create: `packages/observability/tests/test_http.py`
- Modify: `requirements-dev.txt`
- Modify: `pyproject.toml`
- Modify: `tests/Dockerfile`

**Interfaces:**
- Consumes: `NETPULSE_METRICS_ENABLED`, `NETPULSE_METRICS_HOST`, and `NETPULSE_METRICS_PORT`.
- Produces: `MetricsHttpConfig.from_env(default_port: int) -> MetricsHttpConfig` and `MetricsServer(config: MetricsHttpConfig, registry: CollectorRegistry)` with idempotent `start() -> None` and `stop() -> None`.

- [ ] **Step 1: Write failing shared-package tests.** Add tests proving disabled-by-default configuration, strict Boolean/port validation, an ephemeral-port HTTP scrape containing a registered gauge, idempotent start/stop, invalid bind failure, and occupied-port failure.

- [ ] **Step 2: Run the focused tests.**

  Run: `python -m pytest packages/observability/tests/test_http.py -q`

  Expected: FAIL because `netpulse_observability` does not exist.

- [ ] **Step 3: Implement the package.** Pin `prometheus-client==0.26.0`; use a per-service `CollectorRegistry`; wrap the official HTTP server without a framework; validate ports in `1..65535`; and keep metrics disabled unless explicitly enabled.

- [ ] **Step 4: Register the package in development tooling.** Add the editable requirement, Python path, coverage source, mypy package, and Docker test-image install.

- [ ] **Step 5: Verify the package and full dependency baseline.**

  Run: `python -m pytest packages/observability/tests packages/contracts/tests -q`

  Run: `python -m ruff check packages/observability pyproject.toml`

  Run: `python -m mypy -p netpulse_observability`

  Expected: all checks PASS on Python 3.12 with PySpark installed from `requirements-dev.txt`.

- [ ] **Step 6: Commit.**

  `git commit -m "feat: add shared Prometheus metrics server"`

### Task 2: Event-ingestor metrics and duplicate outcomes

**Files:**
- Create: `services/event-ingestor/src/netpulse_ingestion/metrics.py`
- Create: `services/event-ingestor/tests/test_metrics.py`
- Modify: `services/event-ingestor/src/netpulse_ingestion/{config.py,cli.py,consumer.py,processor.py,repository.py,publisher.py}`
- Modify: `services/event-ingestor/tests/{test_ingestion_config.py,test_cli.py,test_consumer.py,test_processor.py,test_repository.py,test_publisher.py}`
- Modify: `services/event-ingestor/pyproject.toml`

**Interfaces:**
- Consumes: Task 1's `MetricsHttpConfig` and `MetricsServer`.
- Produces: `IngestionMetrics(registry: CollectorRegistry)`, `EventRepository.persist_event(...) -> bool`, and `ProcessingOutcome.DUPLICATE` while retaining required downstream publication.

- [ ] **Step 1: Write failing config and metrics tests.** Assert port 9101 defaults, explicit enablement, metric names, allowed outcomes (`valid`, `duplicate`, `dead_lettered`, `failed`), retry counts, publication outcomes, processing histogram samples, and last-success timestamp.

- [ ] **Step 2: Run the focused tests.**

  Run: `python -m pytest services/event-ingestor/tests/test_metrics.py services/event-ingestor/tests/test_ingestion_config.py -q`

  Expected: FAIL because ingestion metrics are absent.

- [ ] **Step 3: Make persistence report insertion.** Return `cursor.rowcount == 1` from the raw-event insert, preserve typed idempotent writes, add `ProcessingOutcome.DUPLICATE`, and continue publishing the same validated output for replays.

- [ ] **Step 4: Instrument the workflow.** Inject `IngestionMetrics` into the consumer and publisher; time processing; record retries before backoff; record synchronous publication acknowledgement/failure; and advance last-success only after durable processing and required output acknowledgement.

- [ ] **Step 5: Start and stop metrics with the service.** `healthcheck` must not start a server; `run` starts it before Kafka polling and stops it in `finally`.

- [ ] **Step 6: Verify semantics and metrics.**

  Run: `python -m pytest services/event-ingestor/tests -q`

  Expected: PASS, including duplicate replay publication and operation when no Prometheus scraper exists.

- [ ] **Step 7: Commit.**

  `git commit -m "feat: expose ingestion reliability metrics"`

### Task 3: Agent metrics, Docker fixture, and mandatory Pi configuration

**Files:**
- Create: `services/network-agent/src/netpulse_agent/metrics.py`
- Create: `services/network-agent/tests/test_metrics.py`
- Create: `config/agent-docker.yaml`
- Create: `deployment/pi/bootstrap/agent.env.example`
- Modify: `services/network-agent/src/netpulse_agent/{cli.py,runtime.py,scheduler.py,publisher.py,outbox.py}`
- Modify: `services/network-agent/tests/{test_cli_runtime.py,test_outbox.py,test_publisher.py,test_scheduler.py,test_pi_deployment_config.py}`
- Modify: `services/network-agent/pyproject.toml`
- Modify: `config/agent-pi.yaml`
- Modify: `deployment/systemd/agent.env.example`
- Modify: `deployment/pi/bootstrap/first-boot.sh`
- Modify: `deployment/pi/bootstrap/tests/first_boot_test.sh`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: Task 1's server and the existing collector/outbox interfaces.
- Produces: `AgentMetrics`, `SQLiteOutbox.oldest_pending_age_seconds(now: float | None = None) -> float | None`, Docker identity `container-observer-01`, and Pi metrics endpoint port 9102.

- [ ] **Step 1: Write failing agent metric/outbox tests.** Assert collector outcomes use only the fixed collector names, publication outcomes are acknowledged/failed, queue depth and oldest-pending age update after enqueue/delivery, and the server lifecycle follows `run` only.

- [ ] **Step 2: Run the focused tests.**

  Run: `python -m pytest services/network-agent/tests/test_metrics.py services/network-agent/tests/test_outbox.py -q`

  Expected: FAIL because the metrics and oldest-age query do not exist.

- [ ] **Step 3: Instrument collection and delivery.** Inject metrics into workers and publisher, update queue gauges after each batch, and keep collection/publication functional with no scraper.

- [ ] **Step 4: Add a truthful Docker fixture.** Mount `config/agent-docker.yaml`; use role `container_probe`; disable Wi-Fi and speed tests; keep heartbeat, ping, DNS, and bounded HTTP only where explicitly reachable; retain the named SQLite volume.

- [ ] **Step 5: Enable Pi observability.** Add a non-secret bootstrap environment template with metrics enabled on `0.0.0.0:9102`; require the operator to stage it as `agent.env` before first boot; enable DNS against `192.168.1.254` for `example.com`; preserve wired identity and disabled Wi-Fi/HTTP/speed test; and make first-boot tests prove the staged environment is installed idempotently. Never commit the Pi's device-specific salt.

- [ ] **Step 6: Verify agent and bootstrap behavior.**

  Run: `python -m pytest services/network-agent/tests packages/contracts/tests -q`

  Run: `bash deployment/pi/bootstrap/tests/first_boot_test.sh`

  Run: `bash deployment/pi/tests/preflight_test.sh`

  Expected: all tests PASS and rerunning bootstrap preserves the outbox/user.

- [ ] **Step 7: Commit.**

  `git commit -m "feat: monitor agent collection and outbox health"`

### Task 4: Classifier and Spark streaming metrics

**Files:**
- Create: `services/incident-classifier/src/netpulse_classifier/metrics.py`
- Create: `services/incident-classifier/tests/test_metrics.py`
- Create: `services/stream-processor/src/netpulse_streaming/metrics.py`
- Create: `services/stream-processor/tests/test_metrics.py`
- Modify: `services/incident-classifier/src/netpulse_classifier/{config.py,cli.py,service.py,publisher.py}`
- Modify: `services/incident-classifier/tests/{test_config.py,test_cli.py,test_service.py,test_publisher.py}`
- Modify: `services/incident-classifier/pyproject.toml`
- Modify: `services/stream-processor/src/netpulse_streaming/{config.py,cli.py,sink.py}`
- Modify: `services/stream-processor/tests/{test_config.py,test_sink.py}`
- Modify: `services/stream-processor/pyproject.toml`

**Interfaces:**
- Consumes: Task 1's metrics server.
- Produces: `ClassifierMetrics` on port 9104 and `StreamingMetrics` on port 9103.

- [ ] **Step 1: Write failing classifier tests.** Cover evaluation success/failure, transition states, acknowledged/failed publication, pending-outbox gauge, duration, and last-success time.

- [ ] **Step 2: Write failing Spark tests.** Cover metric/failure batch outcomes, accepted/rejected row counts, duration, last-success time, and server shutdown for both continuous and available-now triggers.

- [ ] **Step 3: Run the focused tests.**

  Run: `python -m pytest services/incident-classifier/tests/test_metrics.py services/stream-processor/tests/test_metrics.py -q`

  Expected: FAIL because both metrics modules are absent.

- [ ] **Step 4: Instrument classifier cycles and publication.** Update metrics only at existing durable boundaries and refresh the backlog gauge from pending rows without changing lifecycle transactions.

- [ ] **Step 5: Instrument Spark sink batches and query lifecycle.** Time the existing bounded writes, count output rows by fixed query kind, record failures before re-raising, and stop the metrics server after queries and Spark stop.

- [ ] **Step 6: Verify both services.**

  Run: `python -m pytest services/incident-classifier/tests services/stream-processor/tests -q`

  Expected: PASS with PySpark installed.

- [ ] **Step 7: Commit.**

  `git commit -m "feat: expose streaming and incident metrics"`

### Task 5: Read-only monitoring identities and SRE reporting views

**Files:**
- Create: `database/migrations/versions/0006_phase5b_sre_views.py`
- Create: `database/init/01-create-monitoring-users.sh`
- Create: `scripts/provision-monitoring-users.sh`
- Modify: `database/tests/test_migration.py`
- Modify: `tests/integration/test_analytics_stack.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: existing heartbeat, failure, incident, and analytics tables.
- Produces: `netpulse_monitor` NOLOGIN role, `netpulse_grafana` and `netpulse_postgres_exporter` logins, `v_sre_agent_status`, and `v_sre_pipeline_status`.

- [ ] **Step 1: Write failing migration and privilege tests.** Assert both views' columns, latest-heartbeat selection, pending incident/failure counts, grants to `netpulse_report`, `pg_monitor` membership, denied base-table writes, and idempotent login provisioning.

- [ ] **Step 2: Run the migration tests.**

  Run: `python -m pytest database/tests/test_migration.py tests/integration/test_analytics_stack.py -q`

  Expected: FAIL because revision 0006 and roles do not exist.

- [ ] **Step 3: Implement revision 0006.** Use stable one-row-per-agent and one-row pipeline grains, UTC timestamps, guarded NULL values, and reversible grants/views.

- [ ] **Step 4: Implement fresh/existing-volume provisioning.** Require `GRAFANA_POSTGRES_PASSWORD` and `POSTGRES_EXPORTER_PASSWORD`, quote them through `psql` variables, create/alter only the two named logins, and grant membership without exposing passwords in logs.

- [ ] **Step 5: Verify migrations and privileges against Docker PostgreSQL.**

  Run: `python -m pytest database/tests/test_migration.py -q`

  Run: `docker compose --profile test run --rm -e NETPULSE_INTEGRATION=1 tests -m integration tests/integration/test_analytics_stack.py -q`

  Expected: PASS on a fresh database and a repeated provisioning call.

- [ ] **Step 6: Commit.**

  `git commit -m "feat: add read-only SRE reporting access"`

### Task 6: Self-hosted monitoring Compose profile

**Files:**
- Create: `deployment/observability/prometheus/{prometheus.yml,pi-targets.json}`
- Create: `deployment/observability/alertmanager/alertmanager.yml`
- Create: `deployment/observability/grafana/provisioning/datasources/datasources.yml`
- Create: `tests/test_observability_config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: Tasks 2–5 metrics endpoints and credentials.
- Produces: Compose services `prometheus`, `alertmanager`, `grafana`, `kafka-exporter`, `postgres-exporter`, and `monitoring-init` under profile `monitoring`.

- [ ] **Step 1: Write failing configuration tests.** Parse Compose and YAML to assert pinned images, localhost-only host ports, named volumes, internal application ports, health checks, no public database/Kafka expansion, safe credentials, and an empty-by-default Pi file-SD list.

- [ ] **Step 2: Run the configuration tests.**

  Run: `python -m pytest tests/test_observability_config.py -q`

  Expected: FAIL because monitoring services/assets do not exist.

- [ ] **Step 3: Add the profile and scrape configuration.** Use `prom/prometheus:v3.14.0`, `prom/alertmanager:v0.34.1`, `grafana/grafana:13.2.2`, `prometheuscommunity/postgres-exporter:v0.20.1`, and `danielqsj/kafka-exporter:v1.10.0`; enable application metrics on ports 9101–9104; and keep Pi discovery empty until rendered with its LAN address.

- [ ] **Step 4: Add datasource provisioning.** Configure Prometheus as default and PostgreSQL with the read-only Grafana login; obtain passwords only from container environment variables.

- [ ] **Step 5: Validate native configurations.**

  Run: `docker compose --profile monitoring config --quiet`

  Run: `docker run --rm -v "$PWD/deployment/observability/prometheus:/etc/prometheus:ro" prom/prometheus:v3.14.0 promtool check config /etc/prometheus/prometheus.yml`

  Run: `docker run --rm -v "$PWD/deployment/observability/alertmanager:/etc/alertmanager:ro" prom/alertmanager:v0.34.1 amtool check-config /etc/alertmanager/alertmanager.yml`

  Expected: PASS with no floating images or public bindings.

- [ ] **Step 6: Commit.**

  `git commit -m "feat: add self-hosted monitoring profile"`

### Task 7: Recording rules, alerts, dashboards, and runbooks

**Files:**
- Create: `deployment/observability/prometheus/rules/{recording.yml,alerts.yml}`
- Create: `deployment/observability/grafana/provisioning/dashboards/provider.yml`
- Create: `deployment/observability/grafana/dashboards/{platform-health.json,pipeline-reliability.json,network-reliability.json}`
- Create: `docs/runbooks/{target-down.md,kafka-lag.md,postgres-unavailable.md,pipeline-stale.md,dead-letter-growth.md,classifier-stalled.md,incident-outbox-backlog.md,pi-stale.md,pi-outbox-backlog.md}`
- Modify: `tests/test_observability_config.py`

**Interfaces:**
- Consumes: Prometheus metric names from Tasks 2–4 and PostgreSQL views from Task 5.
- Produces: three provisioned dashboards, recording rules for ingestion ratio/p95/freshness/lag/error budget, and actionable Alertmanager alerts.

- [ ] **Step 1: Extend failing asset tests.** Assert dashboard UIDs/titles/datasources, required panels, bounded PromQL, read-only SQL view use, alert names/severities/runbook URLs, zero-traffic guards, and no Pi alerts when file-SD has no target.

- [ ] **Step 2: Run the asset tests.**

  Run: `python -m pytest tests/test_observability_config.py -q`

  Expected: FAIL because rules, dashboards, and runbooks are absent.

- [ ] **Step 3: Add recording and alert rules.** Implement the spec's illustrative 99% success, one-second p95, 60-second active-traffic freshness, lag, dead-letter, classifier, publication-backlog, and Pi freshness/outbox behaviors. Alerts include summary, impact, likely cause, and runbook URL annotations.

- [ ] **Step 4: Provision the dashboards.** Use Prometheus for SRE signals and only `v_daily_probe_reliability`, `v_incident_summary`, `v_sre_agent_status`, and `v_sre_pipeline_status` for PostgreSQL panels.

- [ ] **Step 5: Write matching runbooks.** Each contains symptoms, safety notes, diagnosis commands, remediation, recovery verification, and escalation conditions without destructive reset commands.

- [ ] **Step 6: Verify assets and rules.**

  Run: `python -m pytest tests/test_observability_config.py -q`

  Run: `docker compose --profile monitoring run --rm prometheus promtool check rules /etc/prometheus/rules/*.yml`

  Expected: PASS and all dashboards are discoverable through provisioning.

- [ ] **Step 7: Commit.**

  `git commit -m "feat: provision SRE dashboards and alerts"`

### Task 8: Operator commands, failure drills, documentation, and acceptance

**Files:**
- Create: `scripts/render_pi_metrics_target.py`
- Create: `scripts/verify_observability.py`
- Create: `scripts/failure_drills.py`
- Create: `tests/test_observability_scripts.py`
- Modify: `scripts/{netpulse.ps1,netpulse.sh}`
- Modify: `Makefile`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `docs/{architecture.md,roadmap.md,limitations.md,failure-testing.md,raspberry-pi-setup.md}`

**Interfaces:**
- Consumes: the complete monitoring stack.
- Produces: `monitoring-render`, `monitoring-up`, `monitoring-verify`, `monitoring-down`, and `failure-drill` commands with equivalent PowerShell/Make/POSIX behavior.

- [ ] **Step 1: Write failing command/script tests.** Assert safe Pi target JSON generation from one IPv4/hostname input, refusal of URLs/ports/public wildcard input, API verification of Prometheus targets/Grafana datasources/Alertmanager state, and failure-drill cleanup in `finally`.

- [ ] **Step 2: Run the script tests.**

  Run: `python -m pytest tests/test_observability_scripts.py -q`

  Expected: FAIL because the scripts and commands are absent.

- [ ] **Step 3: Implement operator commands.** `monitoring-render` writes only the generated Pi target file, `monitoring-up` provisions users then starts the profile, `monitoring-verify` performs read-only API/SQL checks, and `monitoring-down` preserves volumes.

- [ ] **Step 4: Implement reversible failure drills.** Cover Kafka stop/start, PostgreSQL stop/start, malformed traffic, and traffic pause; capture timestamps and alert states; never delete volumes; restore every stopped dependency in `finally`.

- [ ] **Step 5: Update CI and documentation.** Add static asset validation and native rule checks; document the mandatory Pi, Docker-agent fixture role, complete target stack, illustrative objectives, dashboards, commands, security boundaries, and exact physical acceptance checklist.

- [ ] **Step 6: Run complete software acceptance.**

  Run: `python -m pytest -m "not integration" --cov --cov-report=term-missing`

  Run: `python -m ruff format --check .`

  Run: `python -m ruff check .`

  Run: `python -m mypy`

  Run: `docker compose --profile monitoring --profile streaming --profile classification --profile analytics --profile test config --quiet`

  Run: `./scripts/netpulse.ps1 monitoring-up`

  Run: `./scripts/netpulse.ps1 monitoring-verify`

  Run: `./scripts/netpulse.ps1 failure-drill`

  Expected: all software checks PASS, expected alerts fire and resolve, and existing replay/deduplication invariants remain green.

- [ ] **Step 7: Perform mandatory physical Pi acceptance.** Follow `docs/raspberry-pi-setup.md` to verify first boot, manual service enablement after backend verification, real collection, Kafka-offline pending records, reboot persistence, backlog publication, PostgreSQL ingestion, Prometheus visibility, Grafana panels, and Pi alert firing/resolution. Record exact results; if hardware is unavailable, leave this task incomplete and state that explicitly.

- [ ] **Step 8: Commit.**

  `git commit -m "docs: add monitored NetPulse operations workflow"`
