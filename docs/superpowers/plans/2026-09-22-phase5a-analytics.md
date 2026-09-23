# Phase 5A Dimensional Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible PostgreSQL dimensional refresh and read-only reporting interface for daily probe reliability and current incident lifecycle.

**Architecture:** Read the event-ID-deduplicated operational tables in one repeatable-read PostgreSQL transaction. Serialize refreshes with a session advisory lock acquired before the transaction, replace selected UTC daily aggregates, replace the current incident snapshot and bridges, and commit a run record with the facts. Stable views expose plain columns to a reporting role that has no base-table privileges.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 17, Alembic, pytest, Docker Compose, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-21-phase5a-analytics-design.md`

## Global Constraints

- The fact source is `network_measurements`, `service_checks`, `agents`, `endpoints`, and `network_incidents`; never use `network_window_metrics` for exact reconciliation.
- Daily grain is one UTC date, agent, endpoint, and `(source_kind, probe_type)`; source kinds are exactly `network_measurement` and `service_check`.
- Use `event_time` in UTC for dates, not ingestion time or the host timezone; range endpoints are inclusive calendar dates.
- Speed tests and heartbeats are excluded; probe success rate is not an availability SLA.
- A selected date is fully replaced even when it has no remaining source rows; incident fact and both bridges are a full current snapshot.
- The whole refresh and successful run record commit together; an error leaves neither partial facts nor a run record.
- Reporting grants cover views only. Passwords and connection strings with credentials remain local and uncommitted.
- Preserve Python 3.12 typing, structured logging, explicit configuration, no swallowed exceptions, and existing at-least-once claims.

## Review Focus

- `--all` after the last source row is deleted must still discover existing fact dates and clear them (Task 3 test).
- A range with `--through-date` before `--from-date`, or just one endpoint, must fail without connecting (Task 2 test).
- A `service_check` with no `total_duration_ms` must have latency count zero and NULL latency sum/mean, not zero latency (Task 3 test).
- An incident with two affected agents and three endpoints must remain one incident in the summary (Task 4 test).
- A failed job after daily replacement but before incident refresh must preserve both old facts and the old run count (Task 4 test).

## File map and ownership

| File | Responsibility |
|---|---|
| `database/migrations/versions/0005_phase5a_analytics.py` | Dimensions, facts, bridges, run ledger, views, read-only group role, grants, downgrade. |
| `database/tests/test_migration.py` | Static migration contract checks. |
| `services/analytics/pyproject.toml`, `Dockerfile` | Installable one-shot analytics package and non-root image. |
| `services/analytics/src/netpulse_analytics/{__init__,__main__,cli,config,repository}.py` | Argument/config validation and transactional SQL refresh. |
| `services/analytics/tests/{test_cli,test_config}.py` | Fast argument and configuration tests. |
| `tests/integration/test_analytics_stack.py` | Live grain, replay, UTC, incident, rollback, and privilege acceptance. |
| `docker-compose.yml`, `requirements-dev.txt`, `pyproject.toml` | Compose and development-package wiring. |
| `scripts/netpulse.ps1`, `scripts/netpulse.sh`, `Makefile`, `scripts/verify_analytics.py` | Cross-platform backfill/verify commands and reconciliation. |
| `docs/analytics.md`, `README.md`, `.env.example` | Scope, metric definitions, credentials, late-data reruns, commands, limitations. |

The data engineer owns migration, Python job, views, and focused tests. The platform/Pi engineer owns only the explicitly assigned Compose/script packaging files; coordinate before either engineer edits a shared file. The lead integrates and verifies. Do not modify Pi agent files for this phase.

---

### Task 1: Relational model, views, and least-privilege role

**Files:**
- Create: `database/migrations/versions/0005_phase5a_analytics.py`
- Modify: `database/tests/test_migration.py`
- Test: `database/tests/test_migration.py`

**Interfaces:**
- Consumes: operational keys and columns defined in migrations `0001` and `0004`.
- Produces: `dim_agent(agent_id)`, `dim_endpoint(endpoint_id)`, `dim_date(date_utc)`, `dim_probe(source_kind,probe_type)`, `fact_reliability_daily` keyed by `(date_utc,agent_id,endpoint_id,source_kind,probe_type)`, `fact_incident(incident_id)`, `bridge_incident_agent`, `bridge_incident_endpoint`, `analytics_job_runs`, `v_daily_probe_reliability`, `v_incident_summary`, and NOLOGIN role `netpulse_report`.

- [ ] **Step 1: Write a failing migration contract test.** Append this exact test to `database/tests/test_migration.py`:

```python
def test_phase5a_migration_has_grains_views_and_restricted_role() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations" / "versions" / "0005_phase5a_analytics.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "0004"' in migration
    for name in (
        "dim_agent", "dim_endpoint", "dim_date", "dim_probe",
        "fact_reliability_daily", "fact_incident", "bridge_incident_agent",
        "bridge_incident_endpoint", "analytics_job_runs",
        "v_daily_probe_reliability", "v_incident_summary",
    ):
        assert name in migration
    assert "CREATE ROLE netpulse_report NOLOGIN" in migration
    assert "GRANT SELECT ON v_daily_probe_reliability, v_incident_summary" in migration
```

- [ ] **Step 2: Confirm red.** Run `python -m pytest database/tests/test_migration.py::test_phase5a_migration_has_grains_views_and_restricted_role -q`; expect `FileNotFoundError`.
- [ ] **Step 3: Create migration `0005`.** Use Alembic `op.execute()` as in migrations `0001`–`0004`. Define the tables with these exact keys and constraints (the executor should use the complete SQL below, including the two views and grants):

```sql
CREATE TABLE dim_agent (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id),
    agent_role TEXT NOT NULL, display_name TEXT NOT NULL
);
CREATE TABLE dim_endpoint (
    endpoint_id TEXT PRIMARY KEY REFERENCES endpoints(endpoint_id),
    endpoint_type TEXT NOT NULL, display_name TEXT NOT NULL
);
CREATE TABLE dim_date (date_utc DATE PRIMARY KEY);
CREATE TABLE dim_probe (
    source_kind TEXT NOT NULL CHECK (source_kind IN ('network_measurement','service_check')),
    probe_type TEXT NOT NULL,
    PRIMARY KEY (source_kind, probe_type)
);
CREATE TABLE fact_reliability_daily (
    date_utc DATE NOT NULL REFERENCES dim_date(date_utc),
    agent_id TEXT NOT NULL REFERENCES dim_agent(agent_id),
    endpoint_id TEXT NOT NULL REFERENCES dim_endpoint(endpoint_id),
    source_kind TEXT NOT NULL, probe_type TEXT NOT NULL,
    total_count BIGINT NOT NULL CHECK (total_count > 0),
    success_count BIGINT NOT NULL CHECK (success_count >= 0),
    failure_count BIGINT NOT NULL CHECK (failure_count >= 0),
    latency_sum_ms DOUBLE PRECISION,
    latency_count BIGINT NOT NULL CHECK (latency_count >= 0),
    packet_loss_sum_pct DOUBLE PRECISION,
    packet_loss_count BIGINT NOT NULL CHECK (packet_loss_count >= 0),
    PRIMARY KEY (date_utc,agent_id,endpoint_id,source_kind,probe_type),
    FOREIGN KEY (source_kind,probe_type) REFERENCES dim_probe(source_kind,probe_type),
    CHECK (success_count + failure_count = total_count),
    CHECK (latency_count <= total_count AND packet_loss_count <= total_count),
    CHECK ((latency_count = 0) = (latency_sum_ms IS NULL)),
    CHECK ((packet_loss_count = 0) = (packet_loss_sum_pct IS NULL))
);
CREATE TABLE fact_incident (
    incident_id UUID PRIMARY KEY,
    start_time TIMESTAMPTZ NOT NULL, end_time TIMESTAMPTZ,
    status TEXT NOT NULL, incident_type TEXT NOT NULL, severity TEXT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL,
    rule_version TEXT NOT NULL, state_revision INTEGER NOT NULL CHECK (state_revision > 0)
);
CREATE TABLE bridge_incident_agent (
    incident_id UUID NOT NULL REFERENCES fact_incident(incident_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES dim_agent(agent_id),
    PRIMARY KEY (incident_id,agent_id)
);
CREATE TABLE bridge_incident_endpoint (
    incident_id UUID NOT NULL REFERENCES fact_incident(incident_id) ON DELETE CASCADE,
    endpoint_id TEXT NOT NULL REFERENCES dim_endpoint(endpoint_id),
    PRIMARY KEY (incident_id,endpoint_id)
);
CREATE TABLE analytics_job_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_date DATE, through_date DATE,
    is_all BOOLEAN NOT NULL,
    daily_rows BIGINT NOT NULL CHECK (daily_rows >= 0),
    incident_rows BIGINT NOT NULL CHECK (incident_rows >= 0),
    completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((is_all AND from_date IS NULL AND through_date IS NULL)
       OR (NOT is_all AND from_date IS NOT NULL AND through_date IS NOT NULL
           AND from_date <= through_date))
);
CREATE VIEW v_daily_probe_reliability AS
SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type,
       total_count, success_count, failure_count,
       100.0 * success_count / NULLIF(total_count,0) AS success_rate_pct,
       latency_count, latency_sum_ms,
       latency_sum_ms / NULLIF(latency_count,0) AS mean_latency_ms,
       packet_loss_count, packet_loss_sum_pct,
       packet_loss_sum_pct / NULLIF(packet_loss_count,0) AS mean_packet_loss_pct
FROM fact_reliability_daily;
CREATE VIEW v_incident_summary AS
SELECT fi.incident_id, fi.start_time, fi.end_time, fi.status,
       fi.incident_type, fi.severity, fi.confidence_score, fi.duration_ms,
       fi.rule_version, fi.state_revision,
       (SELECT COUNT(*) FROM bridge_incident_agent ba
        WHERE ba.incident_id = fi.incident_id) AS affected_agent_count,
       (SELECT COUNT(*) FROM bridge_incident_endpoint be
        WHERE be.incident_id = fi.incident_id) AS affected_endpoint_count
FROM fact_incident fi;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_report') THEN
        CREATE ROLE netpulse_report NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO netpulse_report;
GRANT SELECT ON v_daily_probe_reliability, v_incident_summary TO netpulse_report;
GRANT SELECT, INSERT, UPDATE, DELETE ON dim_agent, dim_endpoint, dim_date,
    dim_probe, fact_reliability_daily, fact_incident, bridge_incident_agent,
    bridge_incident_endpoint, analytics_job_runs TO netpulse_app;
GRANT USAGE, SELECT ON SEQUENCE analytics_job_runs_run_id_seq TO netpulse_app;
```

Migration `downgrade()` drops views, bridges, facts, dimensions, and job ledger in dependency order, then drops `netpulse_report` only if no separately provisioned member depends on it; document that downgrade may require removing local reader membership first. Do not grant the reader role on base tables, sequences, or operational tables. Keep `CREATE ROLE` idempotent because it is a cluster-level object.

- [ ] **Step 4: Confirm green and SQL upgrade.** Run `python -m pytest database/tests/test_migration.py -q`; expect PASS. Run `docker compose up -d --wait postgres` followed by `docker compose run --rm migrate`; expect Alembic at `0005`. Run `docker compose exec -T postgres psql -U netpulse_admin -d netpulse -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM v_daily_probe_reliability"`; expect zero or more rows and exit 0. Do not reset volumes.
- [ ] **Step 5: Commit this independently testable schema change.** `git add database/migrations/versions/0005_phase5a_analytics.py database/tests/test_migration.py && git commit -m "feat: add phase 5a analytics schema and reporting views"`.

### Task 2: Explicit command range and configuration

**Files:**
- Create: `services/analytics/pyproject.toml`, `services/analytics/src/netpulse_analytics/__init__.py`, `services/analytics/src/netpulse_analytics/__main__.py`, `services/analytics/src/netpulse_analytics/config.py`, `services/analytics/src/netpulse_analytics/cli.py`, `services/analytics/tests/test_cli.py`, `services/analytics/tests/test_config.py`
- Modify: `pyproject.toml`, `requirements-dev.txt`
- Test: `services/analytics/tests/test_cli.py`, `services/analytics/tests/test_config.py`

**Interfaces:**
- Produces: `DateSelection(from_date: date | None, through_date: date | None, is_all: bool)`, `parse_selection(argv: list[str] | None) -> DateSelection`, `AnalyticsConfig.from_env() -> AnalyticsConfig`, and `main(argv: list[str] | None = None) -> int`. `main` calls `PostgresAnalyticsRepository(config.database_url).run(selection)` from Task 3.

- [ ] **Step 1: Write failing CLI/config tests.** In `test_cli.py`:

```python
from datetime import date
import pytest
from netpulse_analytics.cli import parse_selection

def test_all_and_inclusive_range() -> None:
    assert parse_selection(["--all"]).is_all
    selected = parse_selection(["--from-date", "2026-09-20", "--through-date", "2026-09-21"])
    assert (selected.from_date, selected.through_date, selected.is_all) == (
        date(2026, 9, 20), date(2026, 9, 21), False
    )

@pytest.mark.parametrize("args", [
    ["--from-date", "2026-09-20"],
    ["--through-date", "2026-09-20"],
    ["--from-date", "2026-09-21", "--through-date", "2026-09-20"],
    ["--all", "--from-date", "2026-09-20", "--through-date", "2026-09-21"],
    ["--from-date", "2026-02-30", "--through-date", "2026-03-01"],
])
def test_invalid_selection_fails_before_connection(args: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_selection(args)
```

In `test_config.py`, use `monkeypatch.setenv("NETPULSE_DATABASE_URL", "postgresql://local@localhost/netpulse")` and assert `AnalyticsConfig.from_env().database_url` equals that string; delete the variable and assert a `ValueError` naming `NETPULSE_DATABASE_URL`. This avoids a committed fallback password.

- [ ] **Step 2: Confirm red.** Run `python -m pytest services/analytics/tests -q`; expect import failure.
- [ ] **Step 3: Add package and minimal code.** `pyproject.toml` for the package uses `hatchling==1.27.0`, Python `>=3.12,<3.13`, `psycopg[binary]==3.2.6`, `structlog==25.2.0`, and console script `netpulse-analytics = "netpulse_analytics.cli:main"`. Add `-e ./services/analytics` to `requirements-dev.txt`, and add `services/analytics/src` to root pytest `pythonpath`, mypy path/package, and coverage source. Use this parser logic:

```python
@dataclass(frozen=True, slots=True)
class DateSelection:
    from_date: date | None
    through_date: date | None
    is_all: bool

def parse_selection(argv: list[str] | None) -> DateSelection:
    parser = argparse.ArgumentParser(description="Refresh NetPulse analytics")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--all", action="store_true")
    choice.add_argument("--from-date", type=date.fromisoformat)
    parser.add_argument("--through-date", type=date.fromisoformat)
    args = parser.parse_args(argv)
    if args.all and args.through_date is not None:
        parser.error("--all cannot be combined with --through-date")
    if not args.all and (args.through_date is None or args.from_date > args.through_date):
        parser.error("provide an inclusive, ordered --from-date/--through-date pair")
    return DateSelection(args.from_date, args.through_date, args.all)
```

`AnalyticsConfig.from_env()` reads only `NETPULSE_DATABASE_URL`, rejects blank/missing values, and never logs credentials. `main()` parses before configuration or connection, configures NetPulse structured logging, invokes repository `run`, logs run ID and row counts without URL, then returns 0; exceptions propagate and yield nonzero process exit. `__main__.py` raises `SystemExit(main())`.

- [ ] **Step 4: Confirm green.** Run `python -m pytest services/analytics/tests -q`, `ruff check services/analytics`, and `mypy services/analytics/src`; expect PASS. The repository import may need a small typed stub `PostgresAnalyticsRepository.run` until Task 3, but do not claim batch behavior yet.
- [ ] **Step 5: Commit.** `git add services/analytics pyproject.toml requirements-dev.txt && git commit -m "feat: add explicit analytics CLI selection"`.

### Task 3: Transactional daily refresh from deduplicated source rows

**Files:**
- Create: `services/analytics/src/netpulse_analytics/repository.py`, `tests/integration/test_analytics_stack.py`
- Test: `tests/integration/test_analytics_stack.py`

**Interfaces:**
- Consumes: `DateSelection` from Task 2 and Task 1 schema.
- Produces: `RefreshResult(run_id: int, daily_rows: int, incident_rows: int)` and `PostgresAnalyticsRepository.run(selection: DateSelection) -> RefreshResult`; Task 4 inserts incident refresh inside this same transaction.

- [ ] **Step 1: Write live failing tests in `tests/integration/test_analytics_stack.py`.** Mark module `pytestmark = pytest.mark.integration` and skip unless `NETPULSE_INTEGRATION=1`, as in `test_phase1_stack.py`. Use `psycopg.connect(os.environ["NETPULSE_DATABASE_URL"])`; insert isolated `agents`, `endpoints`, `raw_events`, and typed rows with UUIDs and unique source offsets, and remove only those fixture rows in `finally`. Use this assertion pattern for each dated fixture:

```python
selection = DateSelection(date(2026, 3, 8), date(2026, 3, 9), False)
PostgresAnalyticsRepository(os.environ["NETPULSE_DATABASE_URL"]).run(selection)
with psycopg.connect(os.environ["NETPULSE_DATABASE_URL"]) as connection:
    rows = connection.execute(
        """SELECT date_utc, SUM(total_count) FROM fact_reliability_daily
           WHERE agent_id = %s GROUP BY date_utc ORDER BY date_utc""",
        (fixture_agent_id,),
    ).fetchall()
assert rows == [(date(2026, 3, 8), 1), (date(2026, 3, 9), 1)]
```

Test these exact cases: two source rows with the same `event_id` using `ON CONFLICT (event_id) DO NOTHING` still aggregate once; 2026-03-08 23:59:59 UTC and 2026-03-09 00:00:00 UTC fall on separate dates despite a `TZ=America/Los_Angeles` process setting; `service_check.total_duration_ms IS NULL` yields `(latency_count,latency_sum_ms,mean_latency_ms)=(0,NULL,NULL)`; adding one historical event leaves facts for other dates untouched until that historical date is explicitly rerun; deleting the only source event for a selected date removes its stale fact; deleting every source event followed by `--all` removes existing fact rows. Compare each count against `COUNT(DISTINCT event_id)` from typed source rows in the same fixture keyspace. Use transaction-safe fixture cleanup and a unique agent/endpoint prefix so concurrent demo data is never deleted; rerun the fixture dates after cleanup to remove their warehouse rows.
- [ ] **Step 2: Confirm red.** Run `./scripts/netpulse.ps1 test-integration` on Windows or `make test-integration` on POSIX; expect the new test to fail because `repository.py` is absent or not implemented.
- [ ] **Step 3: Implement `run` with lock before snapshot.** Connect with `autocommit=True`, acquire `SELECT pg_try_advisory_lock(731945, 5)` before opening the transaction, raise `RuntimeError("analytics refresh already running")` if false, and always unlock in `finally` before closing. Inside `with connection.transaction():`, execute `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`, then `SET LOCAL TIME ZONE 'UTC'`. Resolve `--all` bounds from minimum/maximum UTC dates across both typed tables **and existing daily fact dates**; a fully empty source and fact table is a successful zero-row run. For explicit range, use supplied dates. Upsert Type 1 agents/endpoints from operational tables and probes from the two type columns; insert selected UTC dates with `generate_series` or `SELECT DISTINCT`; delete `fact_reliability_daily WHERE date_utc BETWEEN %s AND %s` before inserting aggregates. Use bound parameters, never interpolated date strings.

```sql
WITH observations AS (
    SELECT (nm.event_time AT TIME ZONE 'UTC')::date AS date_utc,
           nm.agent_id, nm.target_id AS endpoint_id,
           'network_measurement'::text AS source_kind,
           nm.measurement_type AS probe_type, nm.success,
           nm.latency_ms AS latency_ms, nm.packet_loss_pct
    FROM network_measurements nm
    WHERE nm.event_time >= (%(from_date)s::date AT TIME ZONE 'UTC')
      AND nm.event_time < ((%(through_date)s::date + 1) AT TIME ZONE 'UTC')
    UNION ALL
    SELECT (sc.event_time AT TIME ZONE 'UTC')::date,
           sc.agent_id, sc.endpoint_id, 'service_check'::text,
           sc.check_type, sc.success, sc.total_duration_ms, NULL::double precision
    FROM service_checks sc
    WHERE sc.event_time >= (%(from_date)s::date AT TIME ZONE 'UTC')
      AND sc.event_time < ((%(through_date)s::date + 1) AT TIME ZONE 'UTC')
)
INSERT INTO fact_reliability_daily (
    date_utc, agent_id, endpoint_id, source_kind, probe_type,
    total_count, success_count, failure_count,
    latency_sum_ms, latency_count, packet_loss_sum_pct, packet_loss_count
)
SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type,
       COUNT(*), COUNT(*) FILTER (WHERE success), COUNT(*) FILTER (WHERE NOT success),
       SUM(latency_ms), COUNT(latency_ms), SUM(packet_loss_pct), COUNT(packet_loss_pct)
FROM observations
GROUP BY date_utc, agent_id, endpoint_id, source_kind, probe_type;
```

The typed tables' `event_id` primary keys are the deduplication boundary; do not join `raw_events` or Spark windows for counts. Upsert dimensions before facts, including all agents/endpoints named by incident arrays (which already reference operational dimensions). Write `analytics_job_runs` as the final statement of the transaction, return its generated ID and inserted counts after commit. If Task 4 has not yet supplied incident code, use a private `_refresh_incidents(connection) -> int` returning 0, replaced by Task 4 before the phase is accepted.

- [ ] **Step 4: Confirm green.** Run `./scripts/netpulse.ps1 test-integration` or `make test-integration`; expect all daily cases PASS. Run `python -m pytest services/analytics/tests -q`, `ruff check services/analytics tests/integration/test_analytics_stack.py`, and `mypy services/analytics/src`; expect PASS.
- [ ] **Step 5: Commit.** `git add services/analytics/src/netpulse_analytics/repository.py tests/integration/test_analytics_stack.py && git commit -m "feat: rebuild exact daily reliability facts transactionally"`.

### Task 4: Incident snapshot, bridge cardinality, and atomic rollback

**Files:**
- Modify: `services/analytics/src/netpulse_analytics/repository.py`, `tests/integration/test_analytics_stack.py`
- Test: `tests/integration/test_analytics_stack.py`

**Interfaces:**
- Consumes: Task 3's open `connection` inside its repeatable-read transaction.
- Produces: `_refresh_incidents(connection: psycopg.Connection[tuple[Any, ...]]) -> int`; its return value is stored as `incident_rows` in the successful run record.

- [ ] **Step 1: Add failing live tests.** Insert one `network_incidents` fixture with two affected agents and three endpoints, run analytics, and assert one `fact_incident`/view row, two agent bridge rows, three endpoint bridge rows, and summary counts `(2,3)`:

```python
with psycopg.connect(database_url) as connection:
    row = connection.execute(
        """SELECT affected_agent_count, affected_endpoint_count
           FROM v_incident_summary WHERE incident_id = %s""",
        (fixture_incident_id,),
    ).fetchone()
assert row == (2, 3)
```

Update that same source `incident_id` to `status='resolved'`, non-NULL `end_time`, incremented `state_revision`, and new `duration_ms`; rerun and assert the *same* fact key reflects the new revision. Change an affected array and assert the removed bridge row disappears. Inject a failure by monkeypatching `_refresh_incidents` to raise `RuntimeError("injected incident failure")` after daily delete/insert; assert the old daily fact values, incident fact, and `COUNT(*) FROM analytics_job_runs` are unchanged after the failed call. Assert no fact/bridge count is computed from joining both bridges together.
- [ ] **Step 2: Confirm red.** Run `./scripts/netpulse.ps1 test-integration` or `make test-integration`; expect these new assertions to fail.
- [ ] **Step 3: Replace the incident stub with a full refresh in the same transaction.** Delete both bridge tables and `fact_incident`, insert from `network_incidents`, then insert agent and endpoint bridges separately using `jsonb_array_elements_text`, each with `SELECT DISTINCT` to handle duplicate array elements. Use the source `incident_id` as the fact key and copy all spec fields, including `rule_version`, `duration_ms`, `state_revision`, and current status. Keep the two bridge inserts separate; the view's correlated counts from Task 1 do not multiply cardinality. Return `COUNT(*)` of current `fact_incident` rows.

```sql
INSERT INTO bridge_incident_agent (incident_id, agent_id)
SELECT DISTINCT ni.incident_id, member.agent_id
FROM network_incidents ni
CROSS JOIN LATERAL jsonb_array_elements_text(ni.affected_agents) AS member(agent_id);
INSERT INTO bridge_incident_endpoint (incident_id, endpoint_id)
SELECT DISTINCT ni.incident_id, member.endpoint_id
FROM network_incidents ni
CROSS JOIN LATERAL jsonb_array_elements_text(ni.affected_endpoints) AS member(endpoint_id);
```

Keep the run-ledger insert after incident refresh, inside the same transaction. Do not catch and suppress SQL errors. A test monkeypatch should target the private method before the ledger insert so PostgreSQL's context manager rolls back all writes.

- [ ] **Step 4: Confirm green.** Run the Docker integration suite and the analytics unit suite; expect PASS. Run the SQL reconciliation query `SELECT COUNT(*) FROM fact_incident` and compare with `SELECT COUNT(*) FROM network_incidents`; expect equality at a consistent snapshot. Run Ruff and mypy as in Task 3.
- [ ] **Step 5: Commit.** `git add services/analytics/src/netpulse_analytics/repository.py tests/integration/test_analytics_stack.py && git commit -m "feat: snapshot incident lifecycle and bridges atomically"`.

### Task 5: Packaging, reporting login acceptance, documentation, and final verification

**Files:**
- Create: `services/analytics/Dockerfile`, `scripts/verify_analytics.py`, `docs/analytics.md`
- Modify: `docker-compose.yml`, `scripts/netpulse.ps1`, `scripts/netpulse.sh`, `Makefile`, `.env.example`, `README.md`, `tests/integration/test_analytics_stack.py`
- Test: `tests/integration/test_analytics_stack.py`, Compose verification.

**Interfaces:**
- Produces: one-shot `analytics` Compose profile/service and matching `analytics-build`, `analytics-all`, `analytics-verify` commands on Make/POSIX/PowerShell. `analytics-all` invokes `--all`; explicit dates remain available through direct `docker compose --profile analytics run --rm analytics --from-date YYYY-MM-DD --through-date YYYY-MM-DD`.

- [ ] **Step 1: Add a failing reporting-permission integration test.** Pass `NETPULSE_ADMIN_DATABASE_URL` into the `tests` Compose service. In the test, connect as admin, create a uniquely named temporary LOGIN role with `secrets.token_urlsafe(24)` password using `psycopg.sql.Identifier` for the role and `psycopg.sql.Literal` for the password, grant `netpulse_report` to it, and connect with `psycopg.conninfo.make_conninfo`. Assert `SELECT COUNT(*)` succeeds on both views; assert `INSERT INTO dim_date(date_utc) VALUES ('2031-01-01')`, `UPDATE agents SET display_name=display_name`, and `SELECT * FROM network_measurements` raise `psycopg.errors.InsufficientPrivilege`. Roll back each denied statement, close the login session, revoke membership, and drop only that uniquely named test role in `finally`. Never print or persist the password. Run `make test-integration`; expect failure until Compose wiring and role grants are correct.
- [ ] **Step 2: Add packaging and commands.** Build `services/analytics/Dockerfile` from `python:3.12.10-slim-bookworm`, install only `services/analytics`, create/use UID 10001, and use `ENTRYPOINT ["python", "-m", "netpulse_analytics"]`. Add opt-in Compose `analytics` service with `profiles: [analytics]`, dependency on successful `migrate`, and `NETPULSE_DATABASE_URL` pointing to `netpulse_app` using the existing local Compose variables. Keep it one-shot (`restart: "no"`). Add command cases consistently to both scripts and Makefile; `analytics-verify` runs `analytics --all` then executes `scripts/verify_analytics.py` in the `tests` container. The verifier compares source and fact counts grouped by UTC date/source kind, checks `success+failure=total`, checks incident fact/source count equality, and exits nonzero on mismatch. It must not mutate database state or claim coverage for dates it did not inspect.
- [ ] **Step 3: Document exactly what users can trust.** In `docs/analytics.md`, state the two probe source classes, latency meanings (`network_measurements.latency_ms` versus `service_checks.total_duration_ms`), NULL-means-not-measured, UTC date grain, inclusive rerun syntax, no automatic late-data backfill, Type 1 dimension updates, bridge fanout warning, speed-test/heartbeat exclusion, and probe-rate-not-SLA limitation. Explain local reporting login provisioning without a committed password: as admin run `CREATE ROLE netpulse_report_reader LOGIN; GRANT netpulse_report TO netpulse_report_reader;` and then interactive `\password netpulse_report_reader` in `psql`; use only the view names in Power BI. Note a preexisting PostgreSQL volume needs migration plus this manual login setup; no volume reset. Add README link, commands, and truthful Phase 5A capability sentence; add only non-secret variable names to `.env.example` if the command uses them.
- [ ] **Step 4: Verify the complete feasible phase.** Run `make config`, `make lint`, `make typecheck`, `make test`, `make test-integration`, `make analytics-build`, and `make analytics-verify` (PowerShell equivalents on Windows). Run migration SQL checks with `docker compose exec -T postgres psql -U netpulse_admin -d netpulse -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM v_incident_summary"`. Exercise a failing batch and verify rollback, then rerun successfully. Record exact outputs, skips, environmental limits, and remaining work in the Phase 5A completion report before claiming done. Do not fabricate Pi, scale, or availability evidence.
- [ ] **Step 5: Commit packaging/docs after all checks.** `git add services/analytics/Dockerfile scripts/verify_analytics.py docs/analytics.md docker-compose.yml scripts/netpulse.ps1 scripts/netpulse.sh Makefile .env.example README.md tests/integration/test_analytics_stack.py && git commit -m "docs: package and verify phase 5a reporting"`.

## Acceptance and rollback matrix

| Scenario | Expected evidence |
|---|---|
| Duplicate `event_id` replay | Operational typed PK remains one row; rerun fact count unchanged. |
| Historical late arrival | Only its UTC date changes after explicit rerun; other dates' fact rows unchanged. |
| Empty/deleted selected date | Prior fact rows for that date disappear; zero-row successful ledger entry is committed. |
| `--all` after source deletion | Existing fact dates are included in discovery and cleared. |
| UTC midnight/DST | 23:59:59Z and 00:00:00Z are different UTC dates regardless of host timezone. |
| Incident revision/resolution | Same incident key shows latest status, revision, end time, duration. |
| Two agents × three endpoints | One summary incident with counts 2 and 3; no sixfold count. |
| Injected failure | Daily and incident facts plus run count remain at pre-run values. |
| Reporting login | View SELECT succeeds; fact INSERT, operational UPDATE/SELECT fail. |
| SQL migration downgrade rehearsal | On a disposable database only, `alembic downgrade 0004` removes analytics objects and leaves operational rows intact; re-upgrade succeeds. Never downgrade the shared demo database without approval. |

## Self-review notes

- Coverage: each model grain, batch semantic, view, grant, and named acceptance condition in the spec maps to a task/test above.
- Avoid `network_window_metrics` and bridge-to-bridge joins in the implementation; both would produce misleading numbers.
- Do not infer that physical Raspberry Pi validation, dashboards, API, Prometheus, or production availability are included.
- The lock is session-level and acquired before repeatable-read starts, so a waiting or rejected second run cannot continue with a snapshot from before the first run committed.
