# Phase 6 Daily Reliability API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a localhost-only, read-only FastAPI v1 service that provides bounded, deterministic access to NetPulse daily reliability aggregates.

**Architecture:** Add an independent `services/query-api` package whose FastAPI layer depends on a narrow repository protocol. An async psycopg pool uses a dedicated `netpulse_query_api` login inheriting only `netpulse_report`; fixed parameterized SQL reads `v_daily_probe_reliability` with versioned keyset cursors and a matching database index. Docker Compose provisions and runs the service under an opt-in `api` profile bound to loopback.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, Uvicorn, psycopg 3 async pool, PostgreSQL 17, Docker Compose, pytest, HTTPX, Ruff, mypy

**Spec:** `docs/superpowers/specs/2026-10-02-phase6-daily-reliability-api-design.md`

## Global Constraints

- V1 exposes only `GET /healthz`, `GET /v1/reliability/daily`, `/docs`, and `/openapi.json`; no incidents, live measurements, SRE status, writes, or arbitrary SQL.
- Publish container port 8000 only as `127.0.0.1:8000`; do not add CORS, authentication, LAN exposure, or proxy configuration.
- Read only `v_daily_probe_reliability` through `netpulse_query_api`, which inherits `netpulse_report` and receives no application or administrator credentials.
- Use fixed parameterized SQL, read-only transactions, a bounded async pool, bounded acquisition and statement timeouts, and at most 201 fetched rows.
- Order by `date_utc DESC, agent_id, endpoint_id, source_kind, probe_type`; the cursor contains the complete ordering key and an effective-filter fingerprint.
- Dates are UTC calendar dates; `from_date` and `through_date` are paired, inclusive, ordered, and span no more than 366 days.
- Default `limit` is 50 and the accepted range is 1 through 200; identifier filters are exact, case-sensitive, nonblank, and at most 128 characters.
- Never log connection strings, credentials, cursor contents, identifier/filter values, raw database exceptions, or SQL parameters.
- Preserve all pre-existing worktree changes and add only phase-specific commits.

## Review Focus

- A cursor reused with different filters must return 422 rather than navigating a different result set; Task 2 pins the fingerprint check and Task 4 pins the HTTP mapping.
- Pages whose rows share `date_utc` must neither repeat nor skip rows; Tasks 2 and 3 exercise the complete five-field ordering key.
- Inverted or 367-day date ranges must return 422 before a database call; Tasks 1 and 4 exercise both cases.
- Whitespace-only identifiers and unknown query parameters must return 422 instead of broadening a query; Tasks 1 and 4 exercise both cases.
- Pool and PostgreSQL failures containing connection details must produce only generic 503 responses and scrubbed logs; Task 4 exercises both surfaces.

---

### Task 1: Package foundation, configuration, and contract models

**Files:**
- Create: `services/query-api/pyproject.toml`
- Create: `services/query-api/src/netpulse_query_api/__init__.py`
- Create: `services/query-api/src/netpulse_query_api/config.py`
- Create: `services/query-api/src/netpulse_query_api/models.py`
- Create: `services/query-api/tests/test_config.py`
- Create: `services/query-api/tests/test_models.py`
- Modify: `requirements-dev.txt`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `QueryApiConfig.from_env() -> QueryApiConfig` with `database_url: str`, `pool_min_size: int = 1`, `pool_max_size: int = 5`, `pool_acquire_timeout_seconds: float = 2.0`, `statement_timeout_ms: int = 3000`, and `log_level: str = "INFO"`.
- Produces: `SourceKind(StrEnum)`, `DailyReliabilityFilters`, `DailyReliabilityRow`, `DailyReliabilityPage`, and `CursorKey` in `models.py`.
- Produces: `DailyReliabilityFilters.fingerprint_payload() -> dict[str, str | None]`, containing only normalized effective filters in a fixed field order.

- [ ] **Step 1: Write failing configuration and model tests**

Add tests named `test_config_requires_database_url`, `test_config_loads_bounded_defaults`, `test_config_rejects_invalid_pool_and_timeouts`, `test_filters_require_paired_ordered_dates_with_maximum_span`, `test_filters_reject_blank_or_overlong_identifiers`, and `test_page_serializes_iso_dates_nullable_measurements_and_integer_counts`. Assert the exact defaults above; 366 days passes, 367 days and reversed dates fail; whitespace-only and 129-character identifiers fail; nullable aggregate values serialize as JSON `null`.

- [ ] **Step 2: Run the tests and confirm the missing-package failure**

Run: `python -m pytest services/query-api/tests/test_config.py services/query-api/tests/test_models.py -q`

Expected: FAIL because `netpulse_query_api` does not exist.

- [ ] **Step 3: Add the package and development wiring**

Pin runtime dependencies in the service package to `fastapi==0.115.12`, `psycopg[binary,pool]==3.2.6`, `pydantic==2.11.1`, `structlog==25.2.0`, and `uvicorn==0.34.0`; add `httpx==0.28.1` plus editable `./services/query-api` to `requirements-dev.txt`. Add `services/query-api/src` and `netpulse_query_api` to the root pytest, coverage, and mypy configuration.

- [ ] **Step 4: Implement the typed configuration and models**

Use frozen, slotted configuration dataclasses and Pydantic response/filter models. Strip identifier inputs before rejecting blanks but preserve nonblank case and content for exact matching. Reject a pool minimum below 1, maximum below minimum, nonpositive timeouts, and a missing/blank database URL. Constrain aggregate floats to finite values so responses are valid JSON.

- [ ] **Step 5: Run targeted quality checks**

Run: `python -m pytest services/query-api/tests/test_config.py services/query-api/tests/test_models.py -q`

Expected: PASS.

Run: `python -m mypy services/query-api/src/netpulse_query_api/config.py services/query-api/src/netpulse_query_api/models.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit the foundation**

```bash
git add pyproject.toml requirements-dev.txt services/query-api
git commit -m "feat: define query API contract and configuration"
```

### Task 2: Versioned cursor codec

**Files:**
- Create: `services/query-api/src/netpulse_query_api/cursor.py`
- Create: `services/query-api/tests/test_cursor.py`

**Interfaces:**
- Consumes: `CursorKey` and `DailyReliabilityFilters.fingerprint_payload()` from Task 1.
- Produces: `CursorError(ValueError)`, `encode_cursor(key: CursorKey, filters: DailyReliabilityFilters) -> str`, and `decode_cursor(token: str, filters: DailyReliabilityFilters) -> CursorKey`.
- Produces: URL-safe, unpadded base64 JSON schema `{"v":1,"k":[date,agent,endpoint,source,probe],"f":sha256_hex}` with canonical compact/sorted serialization and a 2048-character decode limit.

- [ ] **Step 1: Write failing cursor tests**

Add tests named `test_cursor_round_trip_uses_complete_ordering_key`, `test_cursor_is_stable_for_equivalent_filters`, `test_cursor_rejects_filter_mismatch`, `test_cursor_rejects_unknown_version`, `test_cursor_rejects_oversize_malformed_and_wrong_shape_payloads`, and `test_same_date_rows_produce_distinct_cursors`. Assert every invalid token raises `CursorError` without leaking the token in its message.

- [ ] **Step 2: Run the cursor tests and confirm failure**

Run: `python -m pytest services/query-api/tests/test_cursor.py -q`

Expected: FAIL because `netpulse_query_api.cursor` does not exist.

- [ ] **Step 3: Implement the cursor codec**

Compute the filter digest from UTF-8 canonical JSON of `fingerprint_payload()`. Decode with strict base64 validation after restoring padding, require the exact payload keys and five key fields, validate through `CursorKey`, and collapse all decoding/schema failures into a generic `CursorError("invalid cursor")`; use `CursorError("cursor does not match filters")` only for the fingerprint mismatch.

- [ ] **Step 4: Run the cursor tests**

Run: `python -m pytest services/query-api/tests/test_cursor.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the cursor codec**

```bash
git add services/query-api/src/netpulse_query_api/cursor.py services/query-api/tests/test_cursor.py
git commit -m "feat: add stable reliability query cursors"
```

### Task 3: Index-backed read-only repository

**Files:**
- Create: `database/migrations/versions/0008_phase6_query_api_index.py`
- Create: `services/query-api/src/netpulse_query_api/repository.py`
- Create: `services/query-api/tests/test_repository.py`
- Modify: `database/tests/test_migration.py`

**Interfaces:**
- Consumes: `CursorKey`, `DailyReliabilityFilters`, and `DailyReliabilityRow` from Task 1.
- Produces: `ReliabilityPage(rows: tuple[DailyReliabilityRow, ...], has_more: bool)`.
- Produces: async `ReliabilityRepository` protocol with `health() -> bool` and `list_daily(filters: DailyReliabilityFilters, cursor: CursorKey | None, limit: int) -> ReliabilityPage`.
- Produces: `PostgresReliabilityRepository(pool: AsyncConnectionPool)` implementing that protocol.

- [ ] **Step 1: Write the failing migration and repository tests**

Assert migration `0008` revises `0007`, creates and drops `idx_fact_reliability_daily_api_order` on `(date_utc DESC, agent_id ASC, endpoint_id ASC, source_kind ASC, probe_type ASC)`. Repository tests must assert fixed projection from only `v_daily_probe_reliability`, bound filter parameters, exact mixed-direction `ORDER BY`, the keyset predicate `date_utc < cursor_date OR (date_utc = cursor_date AND (agent_id, endpoint_id, source_kind, probe_type) > (...))`, a requested fetch size of `limit + 1`, truncation to `limit`, and a complete same-date boundary key.

- [ ] **Step 2: Run the tests and confirm failure**

Run: `python -m pytest database/tests/test_migration.py services/query-api/tests/test_repository.py -q`

Expected: FAIL because migration `0008` and the repository do not exist.

- [ ] **Step 3: Add the reversible ordering index**

Create Alembic revision `0008` with only the named mixed-direction index in `upgrade()` and its exact drop in `downgrade()`.

- [ ] **Step 4: Implement the repository**

Build WHERE fragments only from a closed internal mapping; append values separately as psycopg parameters. Acquire from `AsyncConnectionPool`, execute inside a read-only transaction, set the validated integer statement timeout locally, use `dict_row`, and convert rows through `DailyReliabilityRow`. `health()` runs only `SELECT 1` and returns `False` for psycopg pool/connection errors; `list_daily()` lets dependency exceptions reach the HTTP error mapper.

- [ ] **Step 5: Run targeted tests and type checking**

Run: `python -m pytest database/tests/test_migration.py services/query-api/tests/test_repository.py -q`

Expected: PASS.

Run: `python -m mypy services/query-api/src/netpulse_query_api/repository.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit the query engine**

```bash
git add database/migrations/versions/0008_phase6_query_api_index.py database/tests/test_migration.py services/query-api/src/netpulse_query_api/repository.py services/query-api/tests/test_repository.py
git commit -m "feat: add index-backed reliability repository"
```

### Task 4: FastAPI application, lifespan, and safe failures

**Files:**
- Create: `services/query-api/src/netpulse_query_api/api.py`
- Create: `services/query-api/src/netpulse_query_api/main.py`
- Create: `services/query-api/tests/test_api.py`
- Create: `services/query-api/tests/test_main.py`

**Interfaces:**
- Consumes: Task 1 configuration/models, Task 2 codec, and Task 3 `ReliabilityRepository`.
- Produces: `build_app(repository: ReliabilityRepository, *, lifespan: Callable[[FastAPI], AsyncContextManager[None]] | None = None) -> FastAPI` for isolated contract tests and production lifecycle injection.
- Produces: `create_app() -> FastAPI` for Uvicorn factory startup; it loads configuration, opens/closes `AsyncConnectionPool`, creates `PostgresReliabilityRepository`, and delegates routes to the same application builder.
- Produces: `GET /healthz` and `GET /v1/reliability/daily` with the exact spec response shapes and `X-Request-ID` on every response.

- [ ] **Step 1: Write failing API contract tests**

Using `TestClient` and an async fake repository, add tests for health 200/503, empty and populated pages, next-cursor generation, all filters, default/maximum limit, OpenAPI paths, and disabled CORS. Add explicit tests that unknown parameters, blank identifiers, incomplete/reversed/367-day ranges, malformed cursors, and filter-mismatched cursors return 422 without calling the repository.

- [ ] **Step 2: Write failing request-ID and dependency-failure tests**

Assert an absent ID produces a UUID; printable ASCII up to 128 characters is echoed; CR/LF, non-ASCII, and 129 characters produce a generated UUID. Make the fake repository raise pool timeout, psycopg connection, statement timeout, and unexpected exceptions whose messages include a fabricated credential URL; assert dependency failures return only `{"detail":"database unavailable"}` with 503, unexpected failures return only `{"detail":"internal server error"}` with 500, and captured logs contain neither the URL nor raw exception text.

- [ ] **Step 3: Run the API tests and confirm failure**

Run: `python -m pytest services/query-api/tests/test_api.py services/query-api/tests/test_main.py -q`

Expected: FAIL because the application modules do not exist.

- [ ] **Step 4: Implement routes, strict query parsing, middleware, and exception mapping**

Reject unknown query keys before Pydantic parsing. Keep error details stable: `invalid query parameters`, `invalid cursor`, `cursor does not match filters`, `database unavailable`, and `internal server error`. Log request ID, route template, status, elapsed milliseconds, and returned row count only. Configure FastAPI title `NetPulse Query API`, version `1.0.0`, `/docs`, and `/openapi.json`; do not install CORS middleware.

- [ ] **Step 5: Implement production lifespan and Uvicorn factory**

Create the async pool with `open=False`, Task 1 bounds/timeouts, `default_transaction_read_only=on`, and no connection-string logging. Open it at startup, close it at shutdown, and use `uvicorn netpulse_query_api.main:create_app --factory --host 0.0.0.0 --port 8000` only inside the container; host exposure remains a Compose concern.

- [ ] **Step 6: Run API tests, lint, and type checking**

Run: `python -m pytest services/query-api/tests -q`

Expected: PASS.

Run: `python -m ruff check services/query-api && python -m mypy services/query-api/src/netpulse_query_api`

Expected: both PASS.

- [ ] **Step 7: Commit the HTTP service**

```bash
git add services/query-api/src/netpulse_query_api/api.py services/query-api/src/netpulse_query_api/main.py services/query-api/tests/test_api.py services/query-api/tests/test_main.py
git commit -m "feat: expose daily reliability query API"
```

### Task 5: Least-privilege provisioning and Compose deployment

**Files:**
- Create: `database/init/02-create-query-api-user.sh`
- Create: `services/query-api/Dockerfile`
- Create: `tests/test_query_api_deployment.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `database/tests/test_migration.py`

**Interfaces:**
- Consumes: `netpulse_report` created by migration `0005` and `create_app` from Task 4.
- Produces: idempotent `netpulse_query_api` LOGIN provisioning from `QUERY_API_POSTGRES_PASSWORD`.
- Produces: Compose services `query-api-init` and `query-api`, both under profile `api`; API is reachable at `http://127.0.0.1:8000`.

- [ ] **Step 1: Write failing deployment and provisioning tests**

Assert the init script requires `QUERY_API_POSTGRES_PASSWORD`, supplies it to psql with `--set`, creates or rotates `netpulse_query_api` using `format(... %L ...)`, and grants only `netpulse_report`. Assert Compose gives admin credentials only to `query-api-init`; the API URL uses only `netpulse_query_api`; both services use profile `api`; the API port is exactly `127.0.0.1:8000:8000`; dependencies wait for migration and provisioning; the health check calls `/healthz`; and the image runs UID/GID 10001 without write-capable credentials.

- [ ] **Step 2: Run deployment tests and confirm failure**

Run: `python -m pytest tests/test_query_api_deployment.py database/tests/test_migration.py -q`

Expected: FAIL because the script, image, and Compose services do not exist.

- [ ] **Step 3: Add idempotent fresh-volume and existing-volume provisioning**

Make the script work both under `/docker-entrypoint-initdb.d` and with `PGHOST=postgres` after migration. Pass `QUERY_API_POSTGRES_PASSWORD` into the PostgreSQL container for first initialization and into `query-api-init` for existing volumes. Never print the password or connection URL.

- [ ] **Step 4: Add the non-root image and Compose profile**

Build from `python:3.12.10-slim-bookworm`, install only `services/query-api`, create UID/GID 10001, use the Task 4 Uvicorn factory command, and implement the health check with Python `urllib` rather than adding curl. Set pool and timeout defaults explicitly in Compose and bind only loopback.

- [ ] **Step 5: Validate deployment configuration**

Run: `python -m pytest tests/test_query_api_deployment.py database/tests/test_migration.py -q`

Expected: PASS.

Run: `docker compose --profile api config --quiet`

Expected: exit 0 with no output.

- [ ] **Step 6: Commit deployment wiring**

```bash
git add .env.example docker-compose.yml database/init/02-create-query-api-user.sh database/tests/test_migration.py services/query-api/Dockerfile tests/test_query_api_deployment.py
git commit -m "feat: deploy query API with read-only identity"
```

### Task 6: Live acceptance, operator commands, and v1 documentation

**Files:**
- Create: `tests/test_query_api_integration.py`
- Create: `scripts/verify_query_api.py`
- Create: `docs/query-api.md`
- Modify: `docker-compose.yml`
- Modify: `scripts/netpulse.sh`
- Modify: `scripts/netpulse.ps1`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `docs/roadmap.md`
- Modify: `tests/test_query_api_deployment.py`

**Interfaces:**
- Consumes: the running `query-api`, admin test URL, and `NETPULSE_QUERY_API_DATABASE_URL` passed only to the integration-test container.
- Produces: cross-platform `api-build`, `api-up`, `api-verify`, and `api-down` commands.
- Produces: an HTTP/database acceptance test and a two-page operator verification command.

- [ ] **Step 1: Write failing live acceptance tests**

Mark the module `integration`. With admin credentials, idempotently seed the required dimensions from the migration-provided agent/endpoint rows plus at least three uniquely prefixed probe grains on the same future UTC date, commit them, and remove only rows carrying that date/prefix in `finally`. Through `http://query-api:8000`, assert health 200, JSON number/null types, filters, a `limit=2` cursor followed by a second page with no duplicate/missing ordering keys, and filter-mismatched cursor 422. Connect as `netpulse_query_api` and prove the reporting view succeeds while `SELECT` from `network_measurements` plus INSERT/UPDATE/DELETE fail with `InsufficientPrivilege`. Run `EXPLAIN (FORMAT JSON)` on SQL equivalent to the endpoint query with sequential scans disabled and assert both unfiltered and date-bounded forms use `idx_fact_reliability_daily_api_order` with no `Sort` node.

- [ ] **Step 2: Run the acceptance test and confirm it is not yet wired**

Run: `docker compose --profile api --profile test run --rm -e NETPULSE_INTEGRATION=1 tests -p no:cacheprovider tests/test_query_api_integration.py -q`

Expected: FAIL because the API stack/test credentials are not started or passed.

- [ ] **Step 3: Add operator lifecycle commands and verification script**

`api-up` must start PostgreSQL, run migration `0008`, rerun `query-api-init`, and start/build the healthy API. `api-verify` must call `/healthz`, request a first page with `limit=1`, follow `next_cursor` when present, assert disjoint ordering keys, and print counts without printing cursor contents or identifiers. `api-down` stops/removes only API-profile containers and preserves volumes. Mirror behavior in Bash, PowerShell, and Make targets.

- [ ] **Step 4: Wire and run live acceptance**

Pass the API login URL to the tests service only as `NETPULSE_QUERY_API_DATABASE_URL`. Run `./scripts/netpulse.ps1 api-up`, then the integration command from Step 2, then `./scripts/netpulse.ps1 api-verify`.

Expected: API healthy; integration PASS; verifier reports health and one or two bounded pages without secrets.

- [ ] **Step 5: Write the operator and release documentation**

Document `.env` setup, analytics refresh prerequisite, `api-up/api-verify/api-down`, health and filtered curl examples, paired date bounds, cursor opacity, response fields, error statuses, freshness semantics, the dedicated database role, and a prominent warning that v1 has no authentication and must remain loopback-only. Link the guide from README, add commands to its table, and mark roadmap Phase 6 completed only after the live checks pass.

- [ ] **Step 6: Run full feasible verification**

Run: `python -m pytest -m "not integration" --cov --cov-report=term-missing`

Expected: all unit tests pass, integration tests deselected, coverage at least 80%.

Run: `python -m ruff format --check . && python -m ruff check . && python -m mypy`

Expected: all checks pass.

Run: `docker compose --profile agent --profile demo --profile streaming --profile classification --profile analytics --profile monitoring --profile api --profile test config --quiet`

Expected: exit 0 with no output.

Run: `docker compose --profile api --profile test run --rm -e NETPULSE_INTEGRATION=1 tests -p no:cacheprovider tests/test_query_api_integration.py -q`

Expected: PASS. Record separately any pre-existing unrelated integration failures rather than weakening the query API gate.

- [ ] **Step 7: Commit acceptance and v1 documentation**

```bash
git add Makefile README.md docker-compose.yml docs/query-api.md docs/roadmap.md scripts/netpulse.sh scripts/netpulse.ps1 scripts/verify_query_api.py tests/test_query_api_deployment.py tests/test_query_api_integration.py
git commit -m "docs: complete daily reliability API v1"
```

### Task 7: Final review and release evidence

**Files:**
- Modify only files required to correct findings from review or verification.

**Interfaces:**
- Consumes: the complete Phase 6 implementation from Tasks 1–6.
- Produces: review findings resolved or explicitly documented, and exact final verification evidence.

- [ ] **Step 1: Review the complete branch against the spec**

Inspect every changed file for scope drift, privilege escalation, cursor/SQL disagreement, leaked secrets, unsafe host bindings, unbounded work, and missing tests. Confirm `/v1/reliability/daily` is the only data endpoint.

- [ ] **Step 2: Correct findings with focused tests first**

For each defect, add or tighten the smallest failing test, run it to confirm RED, implement the correction, and rerun it to GREEN. Do not refactor unrelated code.

- [ ] **Step 3: Repeat final verification**

Repeat Task 6 Step 6 plus `git diff --check`. Record exact pass counts, deselections, coverage, migration head, API health result, integration result, and any environment-only limitations.

- [ ] **Step 4: Commit review corrections if any**

```bash
git add <only-reviewed-files>
git commit -m "fix: close query API review findings"
```

If there are no findings, do not create an empty commit.
